# data/fetch_spain.py
#
# Fetches Spanish government bond yields from the ECB's data API.
#
# Public contract (same shape as get_us_yields / get_uk_yields / get_germany_yields):
#
#   get_spain_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#
#   - actual_date is the ISO date of the nearest observation with data
#     (None if nothing was found for any maturity).
#   - yields is a pd.Series of yield percentages indexed by maturity label.
#   - Per-maturity request failures are caught and logged, not raised, so
#     one missing maturity doesn't blank out the whole curve.

import requests
import pandas as pd
from io import StringIO
import streamlit as st

ECB_API_URL = "https://data-api.ecb.europa.eu/service/data/IRS"

# NOTE ON DATA SOURCE:
# See fetch_france.py for the full explanation — the same applies here.
# In short: the ECB "YC" dataflow (used for Germany) has no per-country
# series, only the single euro-area composite curve. A per-country key
# like B.ES.EUR.4F.G_N_A.SV_C_YM.SR_10Y returns a clean JSON 404 "No
# results found" (confirmed against the real backend, not the myracloud
# WAF block a malformed key would trigger), meaning the data simply
# doesn't exist there.
#
# The real per-country series is in the "IRS" dataflow: the "long-term
# interest rate for convergence purposes" — the harmonised ~10-year
# government bond benchmark yield used for the Maastricht convergence
# criteria. It's published MONTHLY, single maturity, so this file (like
# France and Italy) only produces "10Y". classify_curve() needs 2+
# maturities, so Spain's curve shows up as "not enough maturities to
# classify" in the app — expected, handled gracefully already.
#
# Series key format (dataflow "IRS" is already in the URL path, so the key
# itself starts at FREQ): M.<REF_AREA>.L.L40.CI.0000.EUR.N.Z
SPAIN_SERIES = {
    "10Y": "M.ES.L.L40.CI.0000.EUR.N.Z",
}

# Data is monthly, so the search window has to span enough calendar days to
# be sure of catching the nearest monthly observation either side.
SEARCH_WINDOW_DAYS = 45


def _fetch_series(series_key, date, window_days=SEARCH_WINDOW_DAYS):
    """
    Fetch one maturity's series from the ECB API.

    Returns (matched_date: str, value: float) for the observation closest
    to `date`, or None if nothing was found in the search window.
    """
    target = pd.Timestamp(date)
    start = (target - pd.Timedelta(days=window_days)).date().isoformat()
    end = (target + pd.Timedelta(days=window_days)).date().isoformat()

    response = requests.get(
        f"{ECB_API_URL}/{series_key}",
        params={"format": "csvdata", "startPeriod": start, "endPeriod": end},
        headers={"Accept": "text/csv"},
        timeout=30,
    )
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
def get_spain_yields(date):
    """
    Fetch Spanish government bond yields for every maturity in
    SPAIN_SERIES, closest to `date`.

    Cached by (date) so repeat requests for the same date are instant and
    don't re-hit the ECB API.
    """
    yields = {}
    actual_date = None

    for maturity, series_key in SPAIN_SERIES.items():
        try:
            result = _fetch_series(series_key, date)
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
