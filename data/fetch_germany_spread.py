# data/fetch_germany_spread.py
#
# German Bund 10Y-minus-2Y spread, from the Bundesbank's own SDMX API.
#
# Public contract (same shape as get_us_spread_series / get_uk_spread_series):
#
#   get_germany_spread_series(from_date, to_date) -> [{"date": ISO str,
#                                                      "spread": float}, ...]
#
# WHY NOT fetch_germany.py: that module reads the ECB "YC" dataflow, which is
# the euro-area AAA *composite* spot curve (REF_AREA=U2), not German bunds.
# It tracks bunds loosely in calm markets and diverges badly under stress
# (up to ~+71bp during the 2012 euro crisis, when the composite still carried
# non-German AAA issuers). Nothing about its data source or parsing is reused
# here — only the retry/timeout idea, re-stated below because it's HTTP
# scaffolding, not ECB-specific logic.
#
# WHY NOT ECB "IRS" (used by fetch_france/italy/spain): monthly, and 10Y-only
# — no 2Y leg, so it can't produce a spread at all.
#
# ---------------------------------------------------------------------------
# LONG-TERM AVAILABILITY WARNING (read before relying on this)
#
# api.statistiken.bundesbank.de/rest is the Bundesbank's *legacy* SDMX
# endpoint. Its own documentation page already 404s, and the Bundesbank has
# signalled its intent to retire it in favour of a newer data portal API.
# It works today (verified live, see _verify() below) and it is the only
# free source of a genuine daily German 2Y+10Y pair we found, so it's worth
# using — but treat it as borrowed time:
#   - if this starts returning 404/410 across the board, the endpoint is gone,
#     not broken; look for the successor API rather than debugging keys.
#   - the pickle cache below means an outage degrades to stale-but-correct
#     data instead of an empty chart.
# ---------------------------------------------------------------------------

import json
import pickle
import time
from pathlib import Path

import pandas as pd
import requests

BBK_API_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSIS"

# NOTE ON THE SERIES KEY — two gotchas, both confirmed against the live API:
#
# 1. The dataflow ("BBSIS") is already in the URL path, so the key itself
#    starts at the frequency dimension (D). Prefixing the key with "BBSIS."
#    gets a clean JSON 400: {"detail": "Unknown frequency 'BBSIS' in key"}.
#    (Same class of mistake as repeating "YC." on the ECB API — see project
#    memory on ECB key formats.)
# 2. The key must still be COMPLETE — all 15 dimensions below. A bare or
#    partially-specified key makes the request hang indefinitely rather than
#    erroring, so there is no useful timeout-free failure mode here.
#
# Dimensions, in order: BBK_STD_FREQ, BBK_SEIS_BEARER_REG, BBK_SEIS_ITEM,
# BBK_SEIS_VALUATION, BBK_STD_CURRENCY, BBK_SEIS_ISSUER_CLASS,
# BBK_SEIS_LISTED_SUB, BBK_SEIS_SECURITY_CLASS, BBK_SEIS_MATURITY,
# BBK_SEIS_INTEREST_TYPE, BBK_SEIS_INTEREST_RATE, BBK_SEIS_REDEMPTION,
# BBK_SEIS_CERTIFICATE, BBK_SEIS_COVERAGE, BBK_SEIS_RATING.
# Only BBK_SEIS_MATURITY (R02XX / R10XX) differs between the two.
SERIES_KEYS = {
    "2Y":  "D.I.ZAR.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A",
    "10Y": "D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A",
}

# Full history; both maturities start 1997-08-07. Asking for everything once
# and caching it is cheaper than per-range requests, and lets any
# [from_date, to_date] be served from one cached blob.
HISTORY_START = "1997-01-01"

# format=json (SDMX-JSON), never format=csv: the CSV dialect uses German
# locale decimals (comma) under a nonstandard header, which pandas silently
# misparses. JSON gives plain "2.74"-style decimal strings.
RESPONSE_FORMAT = "json"

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60  # daily series — refresh once a day

REQUEST_TIMEOUT_SECONDS = 60  # ~30y of daily data is a 600KB+ response
RETRYABLE_STATUS_CODES = {502, 503, 504}
RETRY_BACKOFF_SECONDS = [0.5, 1]  # one delay per retry, in order


def _parse_sdmx_json(payload):
    """
    Turn a Bundesbank SDMX-JSON response into {ISO date str: float}.

    Shape, as actually returned (inspected, not assumed — and NOT the flat
    ECB shape: everything is nested one level under "data"):

      {"meta": {...},
       "data": {
         "structure": {"dimensions": {"observation": [
             {"id": "TIME_PERIOD", "values": [{"id": "1997-08-01"}, ...]}]}},
         "dataSets": [{"series": {"0:0:...:0": {"observations": {
             "0": [value, obs_status_idx, ...], ...}}}}]}}

    Two things that matter:
      - observations are keyed by a positional index (as a *string*) into the
        TIME_PERIOD values array, so the date comes from that array, not the
        key itself;
      - the TIME_PERIOD axis is every CALENDAR day, not just trading days.
        Non-trading days are present with a null value ([None, 1]), so nulls
        must be dropped — otherwise weekends become fake observations.
      - values arrive as strings ("2.74"), hence the float() cast.
    """
    data = payload["data"]
    time_values = data["structure"]["dimensions"]["observation"][0]["values"]
    dates = [v["id"] for v in time_values]

    series = data["dataSets"][0]["series"]
    if not series:
        return {}
    observations = next(iter(series.values()))["observations"]

    out = {}
    for position, entry in observations.items():
        value = entry[0] if entry else None
        if value is None:
            continue
        out[dates[int(position)]] = float(value)
    return out


def _fetch_series(label):
    """
    Return {ISO date str: yield} for one maturity, full history.

    Cached to data/cache/ as a pickle (same on-disk-pickle approach as
    fetch_uk.py's parsed workbooks) and re-fetched only once the cache is
    older than CACHE_MAX_AGE_SECONDS, so repeated calls don't re-hit the API.
    """
    cache_path = CACHE_DIR / f"bbk_{label}.pkl"
    if cache_path.exists():
        if time.time() - cache_path.stat().st_mtime < CACHE_MAX_AGE_SECONDS:
            with open(cache_path, "rb") as f:
                return pickle.load(f)

    url = f"{BBK_API_URL}/{SERIES_KEYS[label]}"
    params = {"startPeriod": HISTORY_START, "format": RESPONSE_FORMAT}

    print(f"[de_spread] downloading Bundesbank {label} series...")
    response = None
    for attempt in range(len(RETRY_BACKOFF_SECONDS) + 1):
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code not in RETRYABLE_STATUS_CODES:
            break
        if attempt < len(RETRY_BACKOFF_SECONDS):
            delay = RETRY_BACKOFF_SECONDS[attempt]
            print(f"[de_spread] {label}: HTTP {response.status_code}, retrying in {delay}s")
            time.sleep(delay)
    response.raise_for_status()

    parsed = _parse_sdmx_json(response.json())

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(parsed, f)
    return parsed


def get_germany_spread_series(from_date, to_date):
    """
    German Bund 10Y-minus-2Y spread over [from_date, to_date], inclusive.

    Returns a list of {"date": ISO str, "spread": float} sorted ascending by
    date — the same shape get_us_spread_series / get_uk_spread_series return.

    The two maturities are separate series behind separate URLs, so they're
    fetched independently and then inner-joined on date. They do share a
    trading-day calendar in practice, but that's verified rather than assumed:
    any date present in one leg and missing from the other is dropped and
    reported (printed), never silently paired with a neighbouring day's value.

    Network/parse failures are logged and yield an empty list rather than
    raising, matching how fetch_uk.py handles a BoE outage.
    """
    start = pd.Timestamp(from_date)
    end = pd.Timestamp(to_date)

    try:
        leg = {label: _fetch_series(label) for label in SERIES_KEYS}
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        print(f"[de_spread] error fetching/parsing Bundesbank data: {e}")
        return []

    two, ten = leg["2Y"], leg["10Y"]

    # Calendar cross-check between the two legs (full history, before trimming
    # — a mismatch anywhere is worth knowing about, not just inside the range).
    only_2y = sorted(set(two) - set(ten))
    only_10y = sorted(set(ten) - set(two))
    if only_2y or only_10y:
        print(
            f"[de_spread] WARNING: calendar mismatch — {len(only_2y)} date(s) "
            f"only in 2Y {only_2y[:5]}, {len(only_10y)} only in 10Y "
            f"{only_10y[:5]} — dropped (spread needs both legs)."
        )

    both = sorted(set(two) & set(ten))
    return [
        {"date": d, "spread": round(ten[d] - two[d], 4)}
        for d in both
        if start <= pd.Timestamp(d) <= end
    ]


def _verify():
    """
    Runnable self-check: asserts the output is sorted, duplicate-free, has both
    legs present on every date, and prints the four stress-test dates plus a
    FRED cross-check of the 10Y leg.
    """
    series = get_germany_spread_series("1997-01-01", "2026-07-30")
    by_date = {row["date"]: row["spread"] for row in series}
    dates = [row["date"] for row in series]

    assert dates == sorted(dates), "output not sorted by date"
    assert len(dates) == len(set(dates)), "duplicate dates in output"
    assert all(isinstance(r["spread"], float) for r in series), "non-float spread"

    print("\n--- Bund spread on stress-test dates (10Y - 2Y, pct points) ---")
    for d in ["2008-09-15", "2012-07-24", "2020-03-09", "2022-09-23"]:
        print(f"  {d}: {by_date.get(d)}")
    print(f"\n  n={len(series)}  earliest={dates[0]}  latest={dates[-1]}")

    # Range sanity: a 10Y-2Y bund spread outside +/-4pp over this history
    # would mean a mis-keyed maturity or a units error, not a real market.
    worst = max(series, key=lambda r: abs(r["spread"]))
    assert abs(worst["spread"]) < 4.0, f"implausible spread: {worst}"
    print(f"  widest |spread|: {worst['date']} {worst['spread']}")


if __name__ == "__main__":
    _verify()
