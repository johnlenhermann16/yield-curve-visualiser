# data/fetch_australia.py
#
# Fetches Australian government bond yields from the OECD's data API.
#
# Public contract (same shape as get_us_yields / get_uk_yields / get_germany_yields):
#
#   get_australia_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
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

# NOTE ON DATA SOURCE:
# The Reserve Bank of Australia does not publish a clean multi-maturity
# REST/JSON API. https://api.rba.gov.au/... was tried directly (several
# paths, several attempts) and the host doesn't accept connections at all
# (TCP connect times out on port 443 every time) — unreliable, as
# anticipated. Falling back to the OECD API for a single 10Y series, as
# instructed.
#
# The OECD's old MEI-style URL (.../AUS.IRLTLT01.ST) is stale — that
# dataflow has been migrated to a newer 7-dimension key structure. The
# working dataflow/key (verified against the live API) is:
#   Dataflow: OECD.SDD.STES,DSD_KEI@DF_KEI
#   Key:      <REF_AREA>.<FREQ>.IRLT.PA._Z._Z._Z
#   (REF_AREA.FREQ.MEASURE.UNIT_MEASURE.ACTIVITY.ADJUSTMENT.TRANSFORMATION)
# IRLT = "Long-term interest rates" (~10-year government bond benchmark),
# PA = percent per annum. Data is MONTHLY, single maturity, so — like
# France/Italy/Spain, which hit the same "no real per-country multi-
# maturity series" wall — this file only produces "10Y".
OECD_API_URL = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_KEI@DF_KEI"

AUSTRALIA_SERIES = {
    "10Y": "AUS.M.IRLT.PA._Z._Z._Z",
}

# Data is monthly, so the search window has to span enough calendar days to
# be sure of catching the nearest monthly observation either side.
SEARCH_WINDOW_DAYS = 45


def _fetch_series(series_key, date, window_days=SEARCH_WINDOW_DAYS):
    """
    Fetch one maturity's series from the OECD API.

    Returns (matched_date: str, value: float) for the observation closest
    to `date`, or None if nothing was found in the search window.
    """
    target = pd.Timestamp(date)
    start = (target - pd.Timedelta(days=window_days)).strftime("%Y-%m")
    end = (target + pd.Timedelta(days=window_days)).strftime("%Y-%m")

    response = requests.get(
        f"{OECD_API_URL}/{series_key}",
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
def get_australia_yields(date):
    """
    Fetch Australian government bond yields for every maturity in
    AUSTRALIA_SERIES, closest to `date`.

    Cached by (date) so repeat requests for the same date are instant and
    don't re-hit the OECD API.
    """
    yields = {}
    actual_date = None

    for maturity, series_key in AUSTRALIA_SERIES.items():
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
