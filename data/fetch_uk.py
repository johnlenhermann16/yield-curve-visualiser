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


def _best_col_for_years(maturity_row, years):
    """
    Return the column index in `maturity_row` whose header value is
    numerically closest to `years`, or None if no numeric header exists.

    Matched by value (not fixed position) because maturity headers can differ
    slightly between the 8 BoE workbooks — never assume column position is
    stable across files.
    """
    best_col = None
    best_diff = float("inf")
    for col_idx in range(1, len(maturity_row)):
        try:
            diff = abs(float(maturity_row[col_idx]) - years)
        except (TypeError, ValueError):
            continue
        if diff < best_diff:
            best_diff = diff
            best_col = col_idx
    return best_col


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
        best_col = _best_col_for_years(maturity_row, years)
        if best_col is not None:
            try:
                yields[label] = float(row[best_col])
            except (TypeError, ValueError):
                print(f"  No data for {label}")

    actual_date = closest_date.date().isoformat() if yields else None
    return actual_date, pd.Series(yields)


def _workbook_spread_frame(zip_bytes, chosen_file):
    """
    Parse one BoE workbook (reusing the on-disk parsed-workbook cache) and
    return a date-indexed DataFrame with '2Y' and '10Y' yield columns, rows
    with a missing 2Y or 10Y dropped.

    NOTE: yields are read by column *label* (data_rows[c]), not row.iloc[c].
    After _get_parsed_workbook does set_index(0), the remaining columns keep
    labels 1..N that line up with the maturity_row header index, so label
    access is what actually maps header col c -> the c-th maturity. (iloc is
    off by one — it lands on the next-longer maturity.)
    """
    maturity_row, data_rows = _get_parsed_workbook(zip_bytes, chosen_file)
    if data_rows.empty:
        return pd.DataFrame(columns=["2Y", "10Y"])

    c2 = _best_col_for_years(maturity_row, TARGET_MATURITIES["2Y"])
    c10 = _best_col_for_years(maturity_row, TARGET_MATURITIES["10Y"])
    frame = pd.DataFrame(
        {
            "2Y": pd.to_numeric(data_rows[c2], errors="coerce"),
            "10Y": pd.to_numeric(data_rows[c10], errors="coerce"),
        },
        index=data_rows.index,
    ).dropna()
    return frame.sort_index()


@st.cache_data(show_spinner=False)
def get_uk_spread_series(from_date, to_date):
    """
    UK 10Y-minus-2Y gilt spread as a date-indexed daily series over
    [from_date, to_date].

    Returns a list of {"date": ISO str, "spread": float} dicts sorted
    ascending by date — the same shape /api/spread returns for the US, so it
    can drop in there later.

    Spans as many of the 8 BoE workbooks as the range needs. Each workbook is
    parsed via _get_parsed_workbook (whose pickle cache means the zip is never
    re-parsed once warm), and @st.cache_data memoises the whole series per
    (from_date, to_date). Duplicate dates and gaps at workbook seams are
    reported (printed) rather than silently dropped/duplicated.
    """
    start = pd.Timestamp(from_date)
    end = pd.Timestamp(to_date)

    try:
        zip_bytes = _get_boe_zip_bytes()
    except requests.RequestException as e:
        print(f"Error downloading BoE data: {e}")
        return []

    with zipfile.ZipFile(BytesIO(zip_bytes)) as z:
        excel_files = sorted(f for f in z.namelist() if f.endswith(".xlsx"))

    # Distinct workbooks covering every year in the range, chronological.
    needed = []
    for year in range(start.year, end.year + 1):
        fname = find_file_for_year(excel_files, year)
        if fname not in needed:
            needed.append(fname)

    frames = []
    ranges = []  # (fname, min_date, max_date) for seam diagnostics
    for fname in needed:
        try:
            frame = _workbook_spread_frame(zip_bytes, fname)
        except Exception as e:
            print(f"Error reading {fname}: {e}")
            continue
        if frame.empty:
            continue
        frames.append(frame)
        ranges.append((fname, frame.index.min(), frame.index.max()))

    if not frames:
        return []

    combined = pd.concat(frames).sort_index()

    # Seam checks: report duplicates (overlapping workbooks) and gaps between
    # the end of one workbook and the start of the next.
    dupes = combined.index[combined.index.duplicated()].unique()
    if len(dupes):
        print(
            f"[uk_spread] WARNING: {len(dupes)} duplicate date(s) across "
            f"workbook seams: {[d.date().isoformat() for d in dupes]} "
            f"— keeping first."
        )
        combined = combined[~combined.index.duplicated(keep="first")]
    for (fa, _, a_max), (fb, b_min, _) in zip(ranges, ranges[1:]):
        gap = (b_min - a_max).days
        flag = "" if gap <= 4 else "  <-- GAP"
        print(
            f"[uk_spread] seam {fa} -> {fb}: {a_max.date()} -> {b_min.date()} "
            f"({gap} calendar days){flag}"
        )

    combined = combined.loc[(combined.index >= start) & (combined.index <= end)]
    spread = combined["10Y"] - combined["2Y"]
    return [
        {"date": d.date().isoformat(), "spread": float(v)}
        for d, v in spread.items()
    ]


def _verify_spread():
    """
    Runnable self-check for get_uk_spread_series: fetches a range crossing the
    2005->2016 and 2016->2025 workbook seams, prints the spread on three
    stress-test dates, and asserts the output has no duplicate dates.
    """
    series = get_uk_spread_series("2005-01-01", "2026-06-30")
    by_date = {row["date"]: row["spread"] for row in series}

    print("\n--- spread on stress-test dates (10Y - 2Y, percentage points) ---")
    for d in ["2008-09-15", "2020-03-09", "2022-09-23"]:
        print(f"  {d}: {by_date.get(d)}")

    dates = [row["date"] for row in series]
    assert len(dates) == len(set(dates)), "duplicate dates in output series!"
    assert dates == sorted(dates), "output series is not sorted by date!"
    print(f"\n  n={len(series)}  earliest={dates[0]}  latest={dates[-1]}")


if __name__ == "__main__":
    _verify_spread()
