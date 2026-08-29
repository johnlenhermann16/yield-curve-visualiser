# api/main.py
#
# FastAPI backend for the Government Bond Yield Curve Visualiser.
#
# This is a thin HTTP layer over the exact same data-fetching functions the
# Streamlit app (app.py) uses. It does NOT import app.py — app.py runs
# Streamlit widgets and st.stop() at module import time, so importing it
# outside `streamlit run` would execute the whole UI. Instead it imports the
# fetcher registry directly from data/countries.py (the single source of
# truth every fetcher is registered in) and re-implements the historical
# context lookup, which is copied verbatim from app.py's
# get_historical_context() so the two stay in sync by construction.
#
# Every fetcher shares one contract (verified by reading each fetch_*.py):
#   get_<country>_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#     - date is an ISO date string, e.g. "2023-01-13"
#     - actual_date is the nearest trading day the data actually came from
#       (can differ from the requested date on a weekend/holiday), or None
#       if nothing was found.
#     - yields is a pd.Series of yield percentages indexed by maturity label
#       (e.g. "1M", "10Y"); empty if the fetch found nothing.
#
# Run with:
#   uvicorn api.main:app --reload

import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fredapi import Fred

from data.countries import COUNTRY_FETCHERS
from data.fetch_uk import get_uk_spread_series
from data.fetch_germany_spread import get_germany_spread_series

FRED_API_KEY = os.environ["FRED_API_KEY"]

app = FastAPI(
    title="Government Bond Yield Curve API",
    description=(
        "HTTP API over the same yield-curve data sources used by the "
        "Streamlit visualiser — per-country government bond yields plus "
        "historical economic context for a given date."
    ),
    version="1.0.0",
)

# Wide-open CORS: this backend serves a separate frontend (the planned React
# app) from a different origin, and it exposes only public, read-only market
# data, so allowing any origin is safe and convenient here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_date(date_str: str) -> str:
    """
    Validate an ISO date string and return it normalised to YYYY-MM-DD.

    Raises HTTP 400 if it isn't a parseable date, so the client gets a clear
    error instead of the failure surfacing deep inside a fetcher.
    """
    try:
        return pd.Timestamp(date_str).date().isoformat()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date '{date_str}'. Use an ISO date like 2023-01-13.",
        )


def _series_to_yield_dict(yields: pd.Series) -> dict:
    """
    Convert a fetcher's pd.Series (indexed by maturity label) into a plain
    JSON-serialisable dict, coercing numpy floats to native floats and
    dropping any NaN values. Order (short → long maturity) is preserved as
    the fetcher returned it.
    """
    result = {}
    for maturity, value in yields.items():
        if pd.isna(value):
            continue
        result[str(maturity)] = float(value)
    return result


def _fetch_one_country(country: str, date_str: str) -> dict:
    """
    Fetch a single country's yields and package the result (or error) into a
    JSON-friendly dict. A per-country failure (unknown country, network
    error, bad response) is caught and reported in the `error` field rather
    than failing the whole request, mirroring how app.py isolates each
    country's fetch.
    """
    fetcher = COUNTRY_FETCHERS.get(country)
    if fetcher is None:
        return {
            "actual_date": None,
            "yields": {},
            "error": f"Unknown country '{country}'.",
        }

    try:
        actual_date, yields = fetcher(date_str)
    except Exception as exc:  # noqa: BLE001 — surface any fetcher failure as data
        print(f"[{country}] fetch failed: {exc!r}")
        return {"actual_date": None, "yields": {}, "error": f"Failed to fetch data for {country}."}

    if yields is None or yields.empty:
        return {
            "actual_date": actual_date,
            "yields": {},
            "error": f"No data available for {country} near {date_str}.",
        }

    return {
        "actual_date": actual_date,
        "yields": _series_to_yield_dict(yields),
        "error": None,
    }


def _historical_context(date_str: str) -> dict:
    """
    Return the broad economic period a date falls into, with a plain-English
    explanation. Copied verbatim from app.py's get_historical_context() so
    the API and the Streamlit app describe each period identically.

    Returns {"title": str, "explanation": str, "color": str}.
    """
    year = pd.Timestamp(date_str).year

    if year < 2007:
        return {
            "title": "Pre-2007: The \"Great Moderation\"",
            "explanation": (
                "Before 2007, the global economy had enjoyed roughly two decades of "
                "low inflation, steady growth and low volatility — economists nicknamed "
                "this the \"Great Moderation\". Central banks like the US Federal Reserve "
                "were gradually raising interest rates back to more normal levels after "
                "cutting them to deal with the early-2000s dot-com bust. Yield curves in "
                "this period tended to look fairly typical (upward-sloping), reflecting "
                "broad confidence that growth would continue."
            ),
            "color": "blue",
        }
    elif 2007 <= year <= 2009:
        return {
            "title": "2007–2009: The Global Financial Crisis",
            "explanation": (
                "This period covers the build-up to and aftermath of the Global "
                "Financial Crisis, triggered by the collapse of the US subprime "
                "mortgage market and the failure of major banks like Lehman Brothers. "
                "Central banks slashed interest rates to near zero in emergency moves "
                "to stop the financial system from seizing up, and the US Federal "
                "Reserve began \"quantitative easing\" (QE) — buying government bonds to "
                "push money into the economy and pull long-term yields down."
            ),
            "color": "orange",
        }
    elif 2010 <= year <= 2015:
        return {
            "title": "2010–2015: Post-Crisis Recovery",
            "explanation": (
                "In the years after the crisis, central banks kept interest rates near "
                "zero — a \"zero interest rate policy\", or ZIRP — to encourage borrowing "
                "and support a fragile recovery. At the same time, several eurozone "
                "countries struggled with unsustainable government debt, causing the "
                "European debt crisis and pushing their bond yields sharply higher. "
                "Yield curves in the US, UK and Germany stayed generally normal but very "
                "flat at the short end, since near-zero policy rates anchored short-term "
                "yields for years."
            ),
            "color": "blue",
        }
    elif 2016 <= year <= 2019:
        return {
            "title": "2016–2019: Gradual Normalisation",
            "explanation": (
                "As the recovery matured, the US Federal Reserve began slowly raising "
                "interest rates back towards more typical levels, a process known as "
                "\"policy normalisation\". Growth expectations stayed modest and inflation "
                "stayed low, so long-term yields didn't rise much even as short-term "
                "yields climbed — this flattened the US yield curve, which briefly "
                "inverted in parts during 2019 and was widely watched as an early "
                "warning sign of a possible slowdown."
            ),
            "color": "blue",
        }
    elif year == 2020:
        return {
            "title": "2020: The COVID-19 Shock",
            "explanation": (
                "When COVID-19 triggered a sudden, severe global shutdown in March "
                "2020, central banks cut interest rates to zero almost overnight and "
                "launched enormous QE programmes to keep credit markets functioning. "
                "Short-term yields collapsed to near zero, while massive government "
                "borrowing and eventual hopes of recovery kept longer-term yields "
                "comparatively higher, so yield curves steepened sharply — a normal "
                "shape, but for crisis-driven reasons rather than confident growth."
            ),
            "color": "orange",
        }
    elif year == 2021:
        return {
            "title": "2021: Recovery and Rising Inflation",
            "explanation": (
                "As economies reopened and stimulus spending flowed through the "
                "system, growth rebounded strongly — but so did inflation, partly due "
                "to supply-chain bottlenecks and surging demand. Markets began pricing "
                "in the likelihood that central banks would soon need to raise interest "
                "rates to bring inflation back under control, which started pushing "
                "short- and medium-term yields upward through the year."
            ),
            "color": "blue",
        }
    elif 2022 <= year <= 2023:
        return {
            "title": "2022–2023: The Fastest Rate Hike Cycle in 40 Years",
            "explanation": (
                "To fight the highest inflation since the early 1980s, central banks — "
                "especially the US Federal Reserve — raised interest rates at the "
                "fastest pace in decades. Short-term yields shot up faster than "
                "long-term yields, because markets expected the hikes to eventually "
                "cause a slowdown and future rate cuts, producing a deep inversion of "
                "the US yield curve and widespread recession fears. The Bank of Japan "
                "was the major outlier through all of this, keeping rates near zero "
                "and defending its yield curve control policy while every other major "
                "central bank hiked aggressively."
            ),
            "color": "red",
        }
    else:
        return {
            "title": "2024–2025: The Rate Cut Cycle Begins",
            "explanation": (
                "With inflation cooling from its 2022 peak, central banks started "
                "cutting interest rates again, moving cautiously to avoid reigniting "
                "price pressures or tipping the economy into recession. As cuts got "
                "underway, short-term yields began falling faster than long-term "
                "yields, and previously inverted curves started to \"re-normalise\" — "
                "moving back towards their typical upward-sloping shape. Meanwhile the "
                "Bank of Japan moved the opposite way, finally abandoning yield curve "
                "control and raising rates for the first time in decades."
            ),
            "color": "blue",
        }


@app.get("/api/health")
def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


@app.get("/api/countries")
def list_countries() -> dict:
    """
    List every country the API can fetch (the keys of the fetcher registry),
    so a frontend can populate its selector without hardcoding the list.
    """
    return {"countries": list(COUNTRY_FETCHERS.keys())}


@app.get("/api/yields")
def yields(
    countries: str = Query(
        ...,
        description="Comma-separated country names, e.g. 'US,UK,Germany'.",
        examples=["US,UK,Germany"],
    ),
    date: str = Query(
        ...,
        description="ISO date, e.g. '2023-01-13'.",
        examples=["2023-01-13"],
    ),
) -> dict:
    """
    Fetch yield-curve data for one or more countries on (or nearest to) a
    given date.

    Countries are fetched in parallel (each is an independent network call),
    and a failure for one country never fails the others — it's reported in
    that country's `error` field instead.
    """
    date_str = _validate_date(date)

    requested = [c.strip() for c in countries.split(",") if c.strip()]
    if not requested:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one country, e.g. countries=US,UK.",
        )

    with ThreadPoolExecutor(max_workers=len(requested)) as executor:
        results = list(
            executor.map(lambda c: (c, _fetch_one_country(c, date_str)), requested)
        )

    return {
        "date": date_str,
        "countries": {country: payload for country, payload in results},
    }


@app.get("/api/spread")
def spread(
    country: str = Query("US", description="Country name: US, UK or Germany."),
    from_: str = Query(
        None,
        alias="from",
        description="ISO start date. Defaults to 1976-06-01 (T10Y2Y series start).",
    ),
    to: str = Query(None, description="ISO end date. Defaults to today."),
) -> dict:
    """
    Return the 2Y10Y spread as a date-indexed time series ({date, spread}).
    US uses FRED's pre-computed T10Y2Y series; UK uses the BoE gilt spot curve
    (10Y minus 2Y, computed in get_uk_spread_series); Germany uses the
    Bundesbank's own daily bund series (get_germany_spread_series — NOT the ECB
    euro-area AAA composite that fetch_germany.py reads, which isn't German
    data). Missing observations are dropped.

    Germany's series starts 1997-08-07, so a request reaching further back
    simply returns fewer rows rather than erroring.
    """
    if country not in ("US", "UK", "Germany"):
        raise HTTPException(
            status_code=400,
            detail="Spread chart currently available for US, UK and Germany only",
        )

    to_str = _validate_date(to) if to else pd.Timestamp.today().date().isoformat()
    from_str = _validate_date(from_) if from_ else "1976-06-01"

    if country == "UK":
        return {"country": country, "data": get_uk_spread_series(from_str, to_str)}

    if country == "Germany":
        return {"country": country, "data": get_germany_spread_series(from_str, to_str)}

    fred = Fred(api_key=FRED_API_KEY)
    series = fred.get_series(
        "T10Y2Y", observation_start=from_str, observation_end=to_str
    ).dropna()

    data = [
        {"date": d.date().isoformat(), "spread": float(v)}
        for d, v in series.items()
    ]
    return {"country": country, "data": data}


@app.get("/api/historical-context")
def historical_context(
    date: str = Query(
        ...,
        description="ISO date, e.g. '2023-01-13'.",
        examples=["2023-01-13"],
    ),
) -> dict:
    """
    Return the broad economic period a date falls into, plus a plain-English
    description — the same context the Streamlit app shows beneath its chart.
    """
    date_str = _validate_date(date)
    context = _historical_context(date_str)
    return {
        "date": date_str,
        "title": context["title"],
        "description": context["explanation"],
        "color": context["color"],
    }
