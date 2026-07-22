# data/fetch_france.py
#
# Fetches French government bond yields from the ECB's data API.
#
# Public contract (same shape as get_us_yields / get_uk_yields / get_germany_yields):
#
#   get_france_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
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
# The originally-assumed approach — reusing Germany's "YC" dataflow pattern
# with a per-country key, e.g. B.FR.EUR.4F.G_N_A.SV_C_YM.SR_10Y — does NOT
# work. Verified directly against the API: it returns a clean JSON 404 "No
# results found" (not the myracloud WAF block that a malformed key
# triggers — see project memory on ECB key formats), which means the
# request reaches the real backend but there's genuinely no data at that
# key. The "YC" dataflow only publishes the single euro-area composite
# curve (REF_AREA=U2, as used in fetch_germany.py) — it has no per-country
# series at all, not even for Germany itself under "DE".
#
# The real per-country series that DOES exist is in the "IRS" (Interest
# Rate Statistics) dataflow: the "long-term interest rate for convergence
# purposes" — the harmonised ~10-year government bond benchmark yield each
# EU member state reports for the Maastricht convergence criteria. It is
# published MONTHLY and as a single maturity point, not a full daily spot
# curve, so unlike Germany/UK/US this file only produces one maturity
# ("10Y"). classify_curve() needs 2+ maturities, so France's curve will
# show up in the app as "not enough maturities to classify" — expected
# and handled gracefully by the existing UI, not a bug.
#
# Series key format (dataflow "IRS" is already in the URL path, so the key
# itself starts at FREQ): M.<REF_AREA>.L.L40.CI.0000.EUR.N.Z
FRANCE_SERIES = {
    "10Y": "M.FR.L.L40.CI.0000.EUR.N.Z",
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
def get_france_yields(date):
    """
    Fetch French government bond yields for every maturity in
    FRANCE_SERIES, closest to `date`.

    Cached by (date) so repeat requests for the same date are instant and
    don't re-hit the ECB API.
    """
    yields = {}
    actual_date = None

    for maturity, series_key in FRANCE_SERIES.items():
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
