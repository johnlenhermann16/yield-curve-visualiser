# data/fetch_us.py
#
# Fetches US Treasury par yields from FRED (Federal Reserve Economic Data).
#
# Public contract (kept the same across fetch_us.py / fetch_uk.py /
# fetch_germany.py so the caller doesn't need to special-case a country —
# useful to know when this logic eventually moves behind a React app's API):
#
#   get_us_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#
#   - date is an ISO date string, e.g. "2023-01-13".
#   - actual_date is the ISO date of the trading day the data actually came
#     from. It can differ from `date` when the requested date falls on a
#     weekend/holiday — we fall back to the nearest trading day with data.
#     It is None if no data could be found for ANY maturity.
#   - yields is a pd.Series of yield percentages indexed by maturity label
#     (e.g. "1Y", "10Y"). It is empty if nothing was found.
#   - This function never raises for "no data" or network errors on a single
#     maturity — those are logged and skipped so one bad maturity doesn't
#     blank out the whole curve. Callers should still be prepared for
#     unexpected exceptions (e.g. a bad API key) and handle them.

from fredapi import Fred
import pandas as pd
import streamlit as st

FRED_API_KEY = "***REMOVED***"

US_SERIES = {
    "1M":  "DGS1MO",
    "3M":  "DGS3MO",
    "6M":  "DGS6MO",
    "1Y":  "DGS1",
    "2Y":  "DGS2",
    "3Y":  "DGS3",
    "5Y":  "DGS5",
    "7Y":  "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}

# How far either side of the requested date we're willing to look for the
# nearest trading day with published data (covers long weekends/holidays).
SEARCH_WINDOW_DAYS = 10


@st.cache_data(show_spinner=False)
def get_us_yields(date):
    """
    Fetch US Treasury yields for every maturity in US_SERIES, using the
    trading day closest to `date` for each one.

    Cached by (date) so repeat requests for the same date are instant and
    don't re-hit the FRED API.
    """
    target = pd.Timestamp(date)
    window_start = target - pd.Timedelta(days=SEARCH_WINDOW_DAYS)
    window_end = target + pd.Timedelta(days=SEARCH_WINDOW_DAYS)

    fred = Fred(api_key=FRED_API_KEY)
    yields = {}
    actual_date = None

    for maturity, series_id in US_SERIES.items():
        try:
            data = fred.get_series(
                series_id,
                observation_start=window_start,
                observation_end=window_end,
            )
            data = data.dropna()

            if len(data) == 0:
                print(f"No data for {maturity}")
                continue

            # Pick the observation whose date is closest to the target,
            # not just the first one in the window — this is what makes
            # weekend/holiday requests fall back to the nearest trading day.
            closest_date = min(data.index, key=lambda d: abs((d - target).days))
            yields[maturity] = data.loc[closest_date]

            if actual_date is None:
                actual_date = closest_date.date().isoformat()

        except Exception as e:
            print(f"Error fetching {maturity}: {e}")

    return actual_date, pd.Series(yields)
