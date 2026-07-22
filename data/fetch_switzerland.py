# data/fetch_switzerland.py
#
# Fetches Swiss government bond yields from the Swiss National Bank's data API.
#
# Public contract (same shape as get_us_yields / get_uk_yields / get_germany_yields):
#
#   get_switzerland_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#
#   - actual_date is the ISO date of the nearest trading day with data
#     (None if nothing was found for any maturity).
#   - yields is a pd.Series of yield percentages indexed by maturity label.
#   - Per-maturity lookups are wrapped individually so one missing maturity
#     doesn't blank out the whole curve.

import time

import requests
import pandas as pd
import streamlit as st

# NOTE ON PARALLEL FETCHING:
# fetch_germany.py had a bug where the ECB API's occasional slow/504
# responses, combined with one HTTP request per maturity fetched
# sequentially, made page loads very slow. This file doesn't have that
# problem in the first place — the SNB cube API returns every maturity in
# ONE request (see the comment below), so there's nothing to parallelize
# across maturities here. What's still worth hardening against a slow SNB
# response is the same bounded retry/timeout approach used in
# fetch_germany.py, applied to this single request.
RETRYABLE_STATUS_CODES = {502, 503, 504}
MAX_RETRIES = 2  # retries AFTER the first attempt (3 attempts total)
RETRY_BACKOFF_SECONDS = [0.5, 1]  # one delay per retry, in order
REQUEST_TIMEOUT_SECONDS = 4

# NOTE ON DATA SOURCE:
# The SNB's "rendoblid" cube turned out to be reliable and, unlike the
# RBA/SNB fallback case anticipated in the brief, didn't need an OECD
# fallback — it actually publishes a full CHF Confederation bond spot
# curve (1Y through 10Y in 1-year steps, then 15Y/20Y/30Y), daily for
# recent years. That's richer than the assumed 2Y/5Y/10Y, so this file
# uses the same maturity set as fetch_germany.py/fetch_france.py for
# consistency with the rest of the app: 1Y, 2Y, 5Y, 10Y, 20Y, 30Y.
#
# Unlike the other fetchers, the cube API has no per-series endpoint — one
# request returns EVERY maturity (plus several unrelated series) at once,
# so there's a single shared HTTP call per date rather than one per
# maturity. Each maturity is still looked up and validated individually
# below (with its own try/except), matching the per-maturity error
# handling of the other fetch files even though the underlying network
# call is shared.
SNB_CUBE_URL = "https://data.snb.ch/api/cube/rendoblid/data/json/en"

# Maturity label -> the series' key fragment inside "EPB@SNB.rendoblid{...}".
SWITZERLAND_SERIES = {
    "1Y":  "1J",
    "2Y":  "2J",
    "5Y":  "5J",
    "10Y": "10J0",
    "20Y": "20J",
    "30Y": "30J",
}

# How far either side of the requested date to search for the nearest
# trading day with published data (covers weekends/holidays).
SEARCH_WINDOW_DAYS = 10


def _fetch_cube(date, window_days=SEARCH_WINDOW_DAYS):
    """
    Fetch the whole rendoblid cube for a date window around `date`.

    Returns {key_fragment: [(pd.Timestamp, float), ...]} for every series
    in the cube (not just the ones we use), so callers can look up
    whichever maturity they need without a second request.
    """
    target = pd.Timestamp(date)
    start = (target - pd.Timedelta(days=window_days)).date().isoformat()
    end = (target + pd.Timedelta(days=window_days)).date().isoformat()

    response = None
    for attempt in range(MAX_RETRIES + 1):
        response = requests.get(
            SNB_CUBE_URL,
            params={"fromDate": start, "toDate": end},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code not in RETRYABLE_STATUS_CODES:
            break
        if attempt < MAX_RETRIES:
            print(
                f"SNB API returned {response.status_code} "
                f"(attempt {attempt + 1}/{MAX_RETRIES + 1}) — retrying in "
                f"{RETRY_BACKOFF_SECONDS[attempt]}s"
            )
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])
    response.raise_for_status()
    data = response.json()

    series_by_key = {}
    for ts in data.get("timeseries", []):
        key = ts["metadata"]["key"]
        # Keys look like "EPB@SNB.rendoblid{1J}" — pull out the "1J" part.
        if "{" not in key or not key.endswith("}"):
            continue
        key_fragment = key[key.index("{") + 1 : -1]
        observations = [
            (pd.Timestamp(v["date"]), float(v["value"]))
            for v in ts.get("values", [])
            if v.get("value") is not None
        ]
        series_by_key[key_fragment] = observations

    return series_by_key


@st.cache_data(show_spinner=False)
def get_switzerland_yields(date):
    """
    Fetch Swiss Confederation bond yields for every maturity in
    SWITZERLAND_SERIES, closest to `date`.

    Cached by (date) so repeat requests for the same date are instant and
    don't re-hit the SNB API.
    """
    target = pd.Timestamp(date)
    yields = {}
    actual_date = None

    try:
        series_by_key = _fetch_cube(date)
    except Exception as e:
        print(f"Error fetching SNB data: {e}")
        return None, pd.Series(dtype=float)

    for maturity, key_fragment in SWITZERLAND_SERIES.items():
        try:
            observations = series_by_key.get(key_fragment, [])
            if not observations:
                print(f"No data for {maturity}")
                continue

            closest_date, value = min(observations, key=lambda obs: abs((obs[0] - target).days))
            yields[maturity] = value
            if actual_date is None:
                actual_date = closest_date.date().isoformat()

        except Exception as e:
            print(f"Error processing {maturity}: {e}")

    return actual_date, pd.Series(yields)
