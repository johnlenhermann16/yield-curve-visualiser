# data/fetch_japan.py
#
# Fetches Japanese Government Bond (JGB) yields from the Ministry of
# Finance's historical yield CSV, falling back to the OECD API (10Y only)
# if the MOF file can't be reached or parsed.
#
# Public contract (same shape as get_us_yields / get_uk_yields / get_germany_yields):
#
#   get_japan_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#
#   - actual_date is the ISO date of the nearest trading day with data
#     (None if nothing was found for any maturity).
#   - yields is a pd.Series of yield percentages indexed by maturity label.
#   - Per-maturity lookups are wrapped individually so one missing maturity
#     doesn't blank out the whole curve.

import re
import time
from io import StringIO

import requests
import pandas as pd
import streamlit as st

# NOTE ON PARALLEL FETCHING:
# fetch_germany.py had a bug where the ECB API's occasional slow/504
# responses, combined with one HTTP request per maturity fetched
# sequentially, made page loads very slow. This file doesn't have that
# problem in the first place — both the MOF CSV and the OECD fallback are
# a single request each (all maturities are sliced out of that one
# response locally, see JAPAN_COLUMNS below), so there's nothing to
# parallelize across maturities here. What's still worth hardening
# against a slow MOF/OECD response is the same bounded retry/timeout
# approach used in fetch_germany.py, applied to these two requests.
RETRYABLE_STATUS_CODES = {502, 503, 504}
MAX_RETRIES = 2  # retries AFTER the first attempt (3 attempts total)
RETRY_BACKOFF_SECONDS = [0.5, 1]  # one delay per retry, in order

# The MOF file is a ~1.1MB one-time download (cached after the first
# fetch), so it gets a more generous timeout than the small OECD fallback
# request — 4s would risk false failures on an otherwise-healthy but slow
# connection downloading that much data.
MOF_CSV_TIMEOUT_SECONDS = 15
OECD_REQUEST_TIMEOUT_SECONDS = 4

# NOTE ON DATA SOURCE:
# The URL given in the brief (.../interest_rate/jgbcm.csv) only publishes a
# rolling window of the ~15 most recent trading days — fine for "today",
# empty for any historical date like 2023-01-13 or 2024-06-01 (verified by
# downloading it: 15 data rows, all within the last three weeks). The MOF
# publishes the full history back to 1974 at jgbcm_all.csv instead
# (13,000+ rows), so that's the file this fetcher actually reads. The file
# is Shift-JIS encoded with Japanese-era dates (e.g. "R5.1.13" = Reiwa 5 =
# 2023-01-13) and 15 fixed maturity columns after the date.
JGB_ALL_CSV_URL = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"

# Column position (0-indexed, right after the date column) -> maturity
# label. The file's 15 columns are fixed, in this order:
# 1,2,3,4,5,6,7,8,9,10,15,20,25,30,40 years. Only the maturities the brief
# asked for (and the rest of the app actually plots) are kept here.
JAPAN_COLUMNS = {
    0: "1Y",
    1: "2Y",
    2: "3Y",
    4: "5Y",
    6: "7Y",
    9: "10Y",
    12: "20Y",
    13: "30Y",
    14: "40Y",
}

# Japanese era -> the Gregorian year that era's "year 1" corresponds to.
# The file only ever uses Showa/Heisei/Reiwa dates (it starts in 1974).
ERA_BASE_YEAR = {
    "S": 1925,  # Showa 1 = 1926
    "H": 1988,  # Heisei 1 = 1989
    "R": 2018,  # Reiwa 1 = 2019
}

ERA_DATE_PATTERN = re.compile(r"^([SHR])(\d+)\.(\d+)\.(\d+)$")

# OECD fallback — see get_japan_yields()'s docstring for why this is only
# ever used as a last resort.
OECD_API_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_KEI@DF_KEI"
    "/JPN.M.IRLT.PA._Z._Z._Z"
)
OECD_SEARCH_WINDOW_DAYS = 45  # OECD series is monthly


def _parse_era_date(raw_date):
    """Convert a Japanese-era date like "R5.1.13" to a pandas Timestamp."""
    match = ERA_DATE_PATTERN.match(raw_date.strip())
    if not match:
        return None
    era, era_year, month, day = match.groups()
    year = ERA_BASE_YEAR[era] + int(era_year)
    return pd.Timestamp(year=year, month=int(month), day=int(day))


@st.cache_data(show_spinner=False)
def _fetch_all_rows():
    """
    Download and parse the full JGB yield history CSV once — shared across
    every call regardless of the requested date, since it's a single
    ~1.1MB file rather than a per-date endpoint.

    Returns a list of (pd.Timestamp, [15 raw column strings]) tuples.
    """
    response = None
    for attempt in range(MAX_RETRIES + 1):
        response = requests.get(JGB_ALL_CSV_URL, timeout=MOF_CSV_TIMEOUT_SECONDS)
        if response.status_code not in RETRYABLE_STATUS_CODES:
            break
        if attempt < MAX_RETRIES:
            print(
                f"MOF API returned {response.status_code} "
                f"(attempt {attempt + 1}/{MAX_RETRIES + 1}) — retrying in "
                f"{RETRY_BACKOFF_SECONDS[attempt]}s"
            )
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])
    response.raise_for_status()
    text = response.content.decode("shift_jis")

    rows = []
    for line in text.splitlines()[2:]:  # skip the two header rows
        fields = line.strip().split(",")
        if len(fields) < 16:
            continue
        parsed_date = _parse_era_date(fields[0])
        if parsed_date is None:
            continue
        rows.append((parsed_date, fields[1:16]))

    return rows


def _fetch_oecd_fallback(date):
    """
    Last-resort fallback if the MOF CSV can't be reached or parsed at all.
    The OECD series is Japan's long-term (10Y-equivalent) government bond
    rate, monthly and single-maturity — it can never produce a full curve,
    it exists purely so the app degrades to one point instead of nothing.
    """
    target = pd.Timestamp(date)
    start = (target - pd.Timedelta(days=OECD_SEARCH_WINDOW_DAYS)).strftime("%Y-%m")
    end = (target + pd.Timedelta(days=OECD_SEARCH_WINDOW_DAYS)).strftime("%Y-%m")

    try:
        response = None
        for attempt in range(MAX_RETRIES + 1):
            response = requests.get(
                OECD_API_URL,
                params={"format": "csvdata", "startPeriod": start, "endPeriod": end},
                headers={"Accept": "text/csv"},
                timeout=OECD_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code not in RETRYABLE_STATUS_CODES:
                break
            if attempt < MAX_RETRIES:
                print(
                    f"OECD API returned {response.status_code} "
                    f"(attempt {attempt + 1}/{MAX_RETRIES + 1}) — retrying in "
                    f"{RETRY_BACKOFF_SECONDS[attempt]}s"
                )
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))
        df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])
        df = df.dropna(subset=["OBS_VALUE"])
        if df.empty:
            return None, pd.Series(dtype=float)

        closest_idx = (df["TIME_PERIOD"] - target).abs().idxmin()
        matched_date = df.loc[closest_idx, "TIME_PERIOD"].date().isoformat()
        value = float(df.loc[closest_idx, "OBS_VALUE"])
        return matched_date, pd.Series({"10Y": value})

    except Exception as e:
        print(f"Error fetching OECD fallback for Japan: {e}")
        return None, pd.Series(dtype=float)


@st.cache_data(show_spinner=False)
def get_japan_yields(date):
    """
    Fetch JGB yields for every maturity in JAPAN_COLUMNS, using the
    trading day closest to `date`.

    Cached by (date) so repeat requests for the same date are instant and
    don't re-parse the CSV or re-hit the OECD fallback.
    """
    target = pd.Timestamp(date)

    try:
        rows = _fetch_all_rows()
    except Exception as e:
        print(f"Error fetching MOF JGB data: {e}")
        return _fetch_oecd_fallback(date)

    if not rows:
        print("MOF JGB data came back empty — falling back to OECD 10Y series")
        return _fetch_oecd_fallback(date)

    closest_date, fields = min(rows, key=lambda r: abs((r[0] - target).days))

    yields = {}
    for col_idx, maturity in JAPAN_COLUMNS.items():
        raw_value = fields[col_idx].strip()
        if raw_value in ("", "-"):
            print(f"No data for {maturity}")
            continue
        try:
            yields[maturity] = float(raw_value)
        except ValueError:
            print(f"Error parsing {maturity}: {raw_value!r}")

    if not yields:
        print("MOF JGB row had no usable maturities — falling back to OECD 10Y series")
        return _fetch_oecd_fallback(date)

    return closest_date.date().isoformat(), pd.Series(yields)
