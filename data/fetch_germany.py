# data/fetch_germany.py
#
# Fetches German Bund yields from the ECB's data API.
#
# Public contract (same shape as get_us_yields / get_uk_yields):
#
#   get_germany_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#
#   - actual_date is the ISO date of the nearest trading day with data
#     (None if nothing was found for any maturity).
#   - yields is a pd.Series of yield percentages indexed by maturity label.
#   - Per-maturity request failures are caught and logged, not raised, so
#     one missing maturity doesn't blank out the whole curve.

import time
import concurrent.futures

import requests
import pandas as pd
from io import StringIO
import streamlit as st

ECB_API_URL = "https://data-api.ecb.europa.eu/service/data/YC"

# NOTE ON THE "No Germany data available" BUG:
# Debugged by hitting the ECB API directly for 2024-01-18 — every single
# maturity request failed with "504 Server Error: Gateway Time-out", and
# the response body was the ECB's own "ECB Data Portal — We are
# experiencing some problems at the moment. Please try again in few
# minutes." page. Confirmed independent of this app (plain curl): the YC
# dataflow, other maturities, other dates, and even a completely unrelated
# ECB dataflow (EXR exchange rates) all 504'd the same way, while the
# ECB's main website stayed up. So it's not a bad series key or a real
# "no data for this date" case — it's the ECB's SDMX data API (fronted by
# a myracloud WAF/gateway) having a transient outage.
#
# First attempt at a fix (retry with 2s/4s/8s backoff, up to 4 attempts,
# maturities fetched one at a time) made page loads far too slow — worst
# case was 6 maturities x up to 4 attempts x up to 30s timeout each,
# entirely sequential. Reworked below: fewer/faster retries, all 6
# maturities fetched in parallel (matching app.py's own thread-pool
# pattern for fetching countries concurrently), and a hard 8-second
# budget on the whole function so a slow/unresponsive ECB never holds up
# the page — whatever maturities finished in time are used, the rest are
# reported as missing rather than blocking.
RETRYABLE_STATUS_CODES = {502, 503, 504}
MAX_RETRIES = 2  # retries AFTER the first attempt (3 attempts total)
RETRY_BACKOFF_SECONDS = [0.5, 1]  # one delay per retry, in order

TOTAL_TIMEOUT_SECONDS = 8  # hard budget for get_germany_yields() as a whole

# Per-request socket timeout. Kept well under TOTAL_TIMEOUT_SECONDS so a
# single hung request can't be the reason a maturity misses the overall
# budget, and so abandoned background threads (see get_germany_yields())
# give up and exit quickly instead of retrying into the void for 20-30s
# after the page has already moved on.
REQUEST_TIMEOUT_SECONDS = 4

# NOTE ON DATA SOURCE:
# The ECB does not publish a Germany-only Bund yield curve. The series below
# ("G_N_A") is the ECB's daily estimated euro area yield curve based on
# AAA-rated central government bonds. Germany is by far the largest and most
# consistent AAA issuer behind it, so this curve is commonly used as a proxy
# for "German Bund yields" — but it is a euro-area composite, not a pure
# single-issuer curve.
#
# Series key format (the dataflow "YC" is already in the URL path, so the
# key itself starts at FREQ — do not repeat "YC." here):
#   B.U2.EUR.4F.G_N_A.SV_C_YM.SR_<maturity>
GERMANY_SERIES = {
    "1Y":  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_1Y",
    "2Y":  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",
    "5Y":  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_5Y",
    "10Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",
    "20Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_20Y",
    "30Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y",
}

# How far either side of the requested date to search for the nearest
# trading day with published data (covers weekends/holidays).
SEARCH_WINDOW_DAYS = 10


def _fetch_series(series_key, date, window_days=SEARCH_WINDOW_DAYS):
    """
    Fetch one maturity's series from the ECB API.

    Returns (matched_date: str, value: float) for the observation closest
    to `date`, or None if nothing was found in the search window.
    """
    target = pd.Timestamp(date)
    start = (target - pd.Timedelta(days=window_days)).date().isoformat()
    end = (target + pd.Timedelta(days=window_days)).date().isoformat()

    response = None
    for attempt in range(MAX_RETRIES + 1):
        response = requests.get(
            f"{ECB_API_URL}/{series_key}",
            params={"format": "csvdata", "startPeriod": start, "endPeriod": end},
            headers={"Accept": "text/csv"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code not in RETRYABLE_STATUS_CODES:
            break
        if attempt < MAX_RETRIES:
            print(
                f"ECB API returned {response.status_code} for {series_key} "
                f"(attempt {attempt + 1}/{MAX_RETRIES + 1}) — retrying in "
                f"{RETRY_BACKOFF_SECONDS[attempt]}s"
            )
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))
    if df.empty:
        return None

    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])
    df = df.dropna(subset=["OBS_VALUE"])
    if df.empty:
        return None

    closest_idx = (df["TIME_PERIOD"] - target).abs().idxmin()
    matched_date = df.loc[closest_idx, "TIME_PERIOD"].date().isoformat()
    value = float(df.loc[closest_idx, "OBS_VALUE"])
    return matched_date, value


@st.cache_data(show_spinner=False)
def get_germany_yields(date):
    """
    Fetch German Bund yields (via the ECB's AAA-rated euro area spot
    curve) for every maturity in GERMANY_SERIES, closest to `date`.

    All 6 maturities are requested in parallel (one thread each) rather
    than one at a time, and the whole call is capped at
    TOTAL_TIMEOUT_SECONDS: whichever maturities haven't finished by then
    are reported as missing rather than holding up the page. Cached by
    (date) so repeat requests for the same date are instant and don't
    re-hit the ECB API.
    """
    yields = {}
    actual_date = None

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(GERMANY_SERIES))
    future_to_maturity = {
        executor.submit(_fetch_series, series_key, date): maturity
        for maturity, series_key in GERMANY_SERIES.items()
    }

    done, not_done = concurrent.futures.wait(
        future_to_maturity, timeout=TOTAL_TIMEOUT_SECONDS
    )

    for future in done:
        maturity = future_to_maturity[future]
        try:
            result = future.result()
            if result is None:
                print(f"No data for {maturity}")
                continue

            matched_date, value = result
            yields[maturity] = value
            if actual_date is None:
                actual_date = matched_date

        except Exception as e:
            print(f"Error fetching {maturity}: {e}")

    for future in not_done:
        maturity = future_to_maturity[future]
        print(f"Timed out waiting for {maturity} (exceeded {TOTAL_TIMEOUT_SECONDS}s budget)")

    # Not-done futures are left running in the background rather than
    # blocked on — shutdown(wait=False) lets get_germany_yields() return
    # immediately instead of waiting out threads we've already given up on.
    executor.shutdown(wait=False, cancel_futures=True)

    return actual_date, pd.Series(yields)
