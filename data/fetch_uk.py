# data/fetch_uk.py
#
# Fetches UK gilt (government bond) yields from the Bank of England's
# published spot curve spreadsheet.
#
# Public contract (same shape as get_us_yields / get_germany_yields):
#
#   get_uk_yields(date: str) -> (actual_date: str | None, yields: pd.Series)
#
#   - actual_date is the ISO date of the nearest trading day in the BoE
#     file to `date` (None if the fetch failed entirely).
#   - yields is a pd.Series of yield percentages indexed by maturity label.
#   - Network/parsing failures are caught here and reported as "no data"
#     (empty Series, actual_date=None) rather than raising, so a BoE outage
#     doesn't crash the whole app.

import requests
import pandas as pd
from io import BytesIO
import zipfile
import streamlit as st
import pickle
import time
from pathlib import Path

BOE_ZIP_URL = (
    "https://www.bankofengland.co.uk/-/media/boe/files/statistics/"
    "yield-curves/glcnominalddata.zip"
)

TARGET_MATURITIES = {
    "2Y":  2.0,
    "5Y":  5.0,
    "10Y": 10.0,
    "20Y": 20.0,
    "30Y": 30.0,
}

CACHE_DIR = Path(__file__).parent / "cache"
ZIP_CACHE_PATH = CACHE_DIR / "glcnominalddata.zip"
ZIP_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _get_boe_zip_bytes():
    """
    Return the raw bytes of the BoE gilt yield curve ZIP, using a local
    on-disk cache so the file is downloaded once and re-downloaded only
    after ZIP_MAX_AGE_SECONDS have elapsed.
    """
    if ZIP_CACHE_PATH.exists():
        age = time.time() - ZIP_CACHE_PATH.stat().st_mtime
        if age < ZIP_MAX_AGE_SECONDS:
            return ZIP_CACHE_PATH.read_bytes()

    print("Downloading BoE gilt yield curve data...")
    response = requests.get(
        BOE_ZIP_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=60
    )
    response.raise_for_status()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ZIP_CACHE_PATH.write_bytes(response.content)
    return response.content


def _parsed_cache_path_for(chosen_file):
    safe_name = chosen_file.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe_name}.pkl"


def _get_parsed_workbook(zip_bytes, chosen_file):
    """
    Return the parsed (maturity_row, data_rows) tuple for `chosen_file`,
    using a pickle cache keyed on the workbook's zip-relative path so the
    same Excel sheet is never re-parsed twice.
    """
    cache_path = _parsed_cache_path_for(chosen_file)
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as z:
        with z.open(chosen_file) as f:
            xl = pd.ExcelFile(f, engine="openpyxl")
            # Use the full spot curve sheet (not short end)
            # Sheet index 4 = "4. spot curve" in the 2016-2024 file
            sheet = [s for s in xl.sheet_names if "spot curve" in s.lower() and "short" not in s.lower()][0]
            print(f"Using sheet: {sheet}")
            df = pd.read_excel(xl, sheet_name=sheet, header=None)

    # Row 3 (index 3) = years as decimals (0.5, 1.0, 1.5 ... 25.0)
    # Row 4 (index 4) onwards = date in col 0, yields in other cols
    maturity_row = df.iloc[3]
    data_rows = df.iloc[4:].copy()
    data_rows.columns = range(len(data_rows.columns))
    data_rows[0] = pd.to_datetime(data_rows[0], errors="coerce")
    data_rows = data_rows.dropna(subset=[0])
    data_rows = data_rows.set_index(0)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump((maturity_row, data_rows), f)

    return maturity_row, data_rows


def find_file_for_year(excel_files, target_year):
    """Pick the workbook (from the BoE zip) whose date range covers target_year."""
    for fname in excel_files:
        parts = fname.replace(".xlsx", "").split("_")[-1].split(" to ")
        try:
            start_yr = int(parts[0].strip())
            end_part = parts[1].strip()
            end_yr = 9999 if "present" in end_part.lower() else int(end_part)
            if start_yr <= target_year <= end_yr:
                return fname
        except (ValueError, IndexError):
            continue
    return excel_files[-1]


@st.cache_data(show_spinner=False)
def get_uk_yields(date):
    """
    Fetch UK gilt yields closest to `date` for every maturity in
    TARGET_MATURITIES.

    The BoE ZIP is cached on disk under data/cache/ and only re-downloaded
    once it's more than 7 days old; each workbook's parsed data is also
    cached on disk (pickle) so it's never re-parsed twice. Combined with
    Streamlit's @st.cache_data on this function, a cold start only pays
    the download+parse cost once ever, not once per session.
    """
    target = pd.Timestamp(date)
    no_data = (None, pd.Series(dtype=float))

    try:
        zip_bytes = _get_boe_zip_bytes()
    except requests.RequestException as e:
        print(f"Error downloading BoE data: {e}")
        return no_data

    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as z:
            excel_files = sorted([f for f in z.namelist() if f.endswith(".xlsx")])
        chosen_file = find_file_for_year(excel_files, target.year)
        print(f"Using file: {chosen_file}")

        maturity_row, data_rows = _get_parsed_workbook(zip_bytes, chosen_file)

    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return no_data

    if data_rows.empty:
        return no_data

    # Nearest available trading day to the requested date — this is what
    # makes a weekend/holiday request fall back automatically.
    available_dates = data_rows.index
    closest_date = available_dates[abs(available_dates - target).argmin()]
    print(f"Closest available date: {closest_date.date()}")

    row = data_rows.loc[closest_date]

    yields = {}
    for label, years in TARGET_MATURITIES.items():
        best_col = None
        best_diff = float("inf")
        for col_idx in range(1, len(maturity_row)):
            val = maturity_row[col_idx]
            try:
                diff = abs(float(val) - years)
                if diff < best_diff:
                    best_diff = diff
                    best_col = col_idx
            except (TypeError, ValueError):
                continue
        if best_col is not None:
            try:
                yields[label] = float(row.iloc[best_col])
            except (TypeError, ValueError):
                print(f"  No data for {label}")

    actual_date = closest_date.date().isoformat() if yields else None
    return actual_date, pd.Series(yields)
