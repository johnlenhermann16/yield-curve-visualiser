# data/fetch_canada.py
#
# Fetches Canadian government bond yields from the Bank of Canada's Valet API.
#
# Public contract (same shape as get_us_yields / get_uk_yields / get_germany_yields):
#
#   get_canada_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#
#   - actual_date is the ISO date of the nearest trading day with data
#     (None if nothing was found for any maturity).
#   - yields is a pd.Series of yield percentages indexed by maturity label.
#   - Per-maturity request failures are caught and logged, not raised, so
#     one missing maturity doesn't blank out the whole curve.

import requests
import pandas as pd
import streamlit as st

VALET_API_URL = "https://www.bankofcanada.ca/valet/observations"

# NOTE ON DATA SOURCE:
# The originally-assumed series IDs (V122539, V122541, V122543, V122547,
# V122551, V122553 — old CANSIM vector codes) return a 404 "Series ... not
# found" from the Valet API; those vectors are no longer published under
# those IDs. The real, current series (found via the Valet series list
# endpoint, /valet/lists/series/json) are the "Benchmark bond yield"
# series below. Canada's benchmark bonds start at 2 years — there's no
# official 1-year benchmark bond yield series, so (unlike the originally
# requested 1Y/2Y/3Y/5Y/7Y/10Y) this file covers 2Y/3Y/5Y/7Y/10Y.
CANADA_SERIES = {
    "2Y":  "BD.CDN.2YR.DQ.YLD",
    "3Y":  "BD.CDN.3YR.DQ.YLD",
    "5Y":  "BD.CDN.5YR.DQ.YLD",
    "7Y":  "BD.CDN.7YR.DQ.YLD",
    "10Y": "BD.CDN.10YR.DQ.YLD",
}

# How far either side of the requested date to search for the nearest
# trading day with published data (covers weekends/holidays).
SEARCH_WINDOW_DAYS = 10


def _fetch_series(series_id, date, window_days=SEARCH_WINDOW_DAYS):
    """
    Fetch one maturity's series from the Bank of Canada Valet API.

    Returns (matched_date: str, value: float) for the observation closest
    to `date`, or None if nothing was found in the search window.
    """
    target = pd.Timestamp(date)
    start = (target - pd.Timedelta(days=window_days)).date().isoformat()
    end = (target + pd.Timedelta(days=window_days)).date().isoformat()

    response = requests.get(
        f"{VALET_API_URL}/{series_id}/json",
        params={"start_date": start, "end_date": end},
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    observations = data.get("observations", [])
    if not observations:
        return None

    dates = []
    values = []
    for obs in observations:
        raw_value = obs.get(series_id, {}).get("v")
        if raw_value is None:
            continue
        dates.append(pd.Timestamp(obs["d"]))
        values.append(float(raw_value))

    if not dates:
        return None

    closest_idx = min(range(len(dates)), key=lambda i: abs((dates[i] - target).days))
    matched_date = dates[closest_idx].date().isoformat()
    value = values[closest_idx]
    return matched_date, value


@st.cache_data(show_spinner=False)
def get_canada_yields(date):
    """
    Fetch Canadian government bond yields for every maturity in
    CANADA_SERIES, closest to `date`.

    Cached by (date) so repeat requests for the same date are instant and
    don't re-hit the Valet API.
    """
    yields = {}
    actual_date = None

    for maturity, series_id in CANADA_SERIES.items():
        try:
            result = _fetch_series(series_id, date)
            if result is None:
                print(f"No data for {maturity}")
                continue

            matched_date, value = result
            yields[maturity] = value
            if actual_date is None:
                actual_date = matched_date

        except Exception as e:
            print(f"Error fetching {maturity}: {e}")

    return actual_date, pd.Series(yields)
