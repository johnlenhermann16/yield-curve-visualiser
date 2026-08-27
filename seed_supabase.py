#!/usr/bin/env python3
"""
seed_supabase.py — one-shot historical data seeder for the yield-curve visualiser.

Fetches full-history yield curves for every country in COUNTRY_FETCHERS
(US, UK, Germany, France, Italy, Spain, Canada, Switzerland, Japan) and
full-history 2Y10Y spread series for US, UK, Germany, then upserts everything
to Supabase in 500-row batches.

Expected Supabase tables:

  CREATE TABLE yield_observations (
    country          TEXT NOT NULL,
    source           TEXT NOT NULL,
    maturity         TEXT NOT NULL,
    observation_date DATE NOT NULL,
    yield_pct        NUMERIC(8,4) NOT NULL,
    frequency        TEXT NOT NULL CHECK (frequency IN ('daily', 'monthly')),
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (country, source, maturity, observation_date)
  );

  CREATE TABLE spread_observations (
    country          TEXT NOT NULL,
    source           TEXT NOT NULL,
    observation_date DATE NOT NULL,
    spread_pct       NUMERIC(8,4) NOT NULL,
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (country, source, observation_date)
  );

Run from the project root with the venv active:
  python seed_supabase.py
"""

import math
import os
import pickle
import re
import time
import zipfile
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import requests
from fredapi import Fred

# ── Load .env (no python-dotenv required) ──────────────────────────────────
def _load_dotenv(path: str = ".env") -> None:
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    except FileNotFoundError:
        pass

_load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
FRED_API_KEY  = os.environ["FRED_API_KEY"]
SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]
CHUNK_SIZE    = 500
TODAY         = pd.Timestamp.today().date().isoformat()

REST_BASE = f"{SUPABASE_URL}/rest/v1"
UPSERT_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "resolution=merge-duplicates",
}

DATA_DIR  = Path(__file__).parent / "data"
CACHE_DIR = DATA_DIR / "cache"

# ── Supabase upload helper ───────────────────────────────────────────────────
def upsert_rows(table: str, rows: list) -> None:
    if not rows:
        print(f"  [skip] no rows for {table}")
        return
    total   = len(rows)
    n_chunks = math.ceil(total / CHUNK_SIZE)
    print(f"  uploading {total} rows to '{table}' in {n_chunks} chunks...")
    for i in range(n_chunks):
        chunk = rows[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        resp = requests.post(
            f"{REST_BASE}/{table}",
            headers=UPSERT_HEADERS,
            json=chunk,
            timeout=60,
        )
        status = "OK" if resp.ok else f"ERROR {resp.status_code}: {resp.text[:200]}"
        print(f"    chunk {i + 1}/{n_chunks} ({len(chunk)} rows) → {status}")


# ═══════════════════════════════════════════════════════════════════════════
# YIELD CURVE FETCHERS
# ═══════════════════════════════════════════════════════════════════════════

# ── US — FRED full history ──────────────────────────────────────────────────
US_FRED_SERIES = {
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

def fetch_us_yields() -> list:
    print("[US] fetching full history from FRED...")
    fred = Fred(api_key=FRED_API_KEY)
    rows = []
    for maturity, series_id in US_FRED_SERIES.items():
        print(f"  {maturity} ({series_id})...")
        try:
            series = fred.get_series(series_id).dropna()
            for date, value in series.items():
                rows.append({
                    "country":          "US",
                    "source":           "FRED",
                    "maturity":         maturity,
                    "observation_date": date.date().isoformat(),
                    "yield_pct":        round(float(value), 4),
                    "frequency":        "daily",
                })
        except Exception as exc:
            print(f"  ERROR {maturity}: {exc}")
    print(f"  {len(rows)} rows")
    return rows


# ── UK — Bank of England zip (all workbooks) ─────────────────────────────────
BOE_ZIP_URL   = (
    "https://www.bankofengland.co.uk/-/media/boe/files/statistics/"
    "yield-curves/glcnominalddata.zip"
)
BOE_ZIP_CACHE = CACHE_DIR / "glcnominalddata.zip"
UK_MATURITIES = {"2Y": 2.0, "5Y": 5.0, "10Y": 10.0, "20Y": 20.0, "30Y": 30.0}

def _boe_zip() -> bytes:
    if BOE_ZIP_CACHE.exists():
        if time.time() - BOE_ZIP_CACHE.stat().st_mtime < 7 * 86400:
            return BOE_ZIP_CACHE.read_bytes()
    print("  downloading BoE zip (cached for 7 days)...")
    resp = requests.get(BOE_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BOE_ZIP_CACHE.write_bytes(resp.content)
    return resp.content

def _best_col(maturity_row, years: float):
    best_col, best_diff = None, float("inf")
    for c in range(1, len(maturity_row)):
        try:
            diff = abs(float(maturity_row[c]) - years)
        except (TypeError, ValueError):
            continue
        if diff < best_diff:
            best_diff, best_col = diff, c
    return best_col

def _parse_boe_workbook(zip_bytes: bytes, fname: str):
    safe  = fname.replace("/", "_").replace("\\", "_")
    cache = CACHE_DIR / f"{safe}.pkl"
    if cache.exists():
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as z, z.open(fname) as fh:
        xl    = pd.ExcelFile(fh, engine="openpyxl")
        sheet = next(s for s in xl.sheet_names if "spot curve" in s.lower() and "short" not in s.lower())
        df    = pd.read_excel(xl, sheet_name=sheet, header=None)
    maturity_row = df.iloc[3]
    data_rows    = df.iloc[4:].copy()
    data_rows.columns = range(len(data_rows.columns))
    data_rows[0] = pd.to_datetime(data_rows[0], errors="coerce")
    data_rows    = data_rows.dropna(subset=[0]).set_index(0)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as fh:
        pickle.dump((maturity_row, data_rows), fh)
    return maturity_row, data_rows

def fetch_uk_yields() -> list:
    print("[UK] fetching full history from BoE workbooks...")
    try:
        zb = _boe_zip()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return []
    with zipfile.ZipFile(BytesIO(zb)) as z:
        excel_files = sorted(f for f in z.namelist() if f.endswith(".xlsx"))

    # keyed on (date, maturity) to deduplicate workbook-seam overlaps
    seen: dict = {}
    for fname in excel_files:
        print(f"  parsing {fname}...")
        try:
            maturity_row, data_rows = _parse_boe_workbook(zb, fname)
        except Exception as exc:
            print(f"  ERROR {fname}: {exc}")
            continue
        col_map = {lbl: _best_col(maturity_row, yrs) for lbl, yrs in UK_MATURITIES.items()}
        for date_idx, row in data_rows.iterrows():
            ds = date_idx.date().isoformat()
            for label, col in col_map.items():
                if col is None:
                    continue
                try:
                    val = float(row[col])
                    if not pd.isna(val):
                        seen[(ds, label)] = round(val, 4)
                except (TypeError, ValueError):
                    pass

    rows = [
        {
            "country":          "UK",
            "source":           "BoE",
            "maturity":         mat,
            "observation_date": ds,
            "yield_pct":        val,
            "frequency":        "daily",
        }
        for (ds, mat), val in seen.items()
    ]
    print(f"  {len(rows)} rows")
    return rows


# ── Germany (yield curve) — ECB YC dataflow, full history ────────────────────
ECB_YC_URL = "https://data-api.ecb.europa.eu/service/data/YC"
GERMANY_YC_SERIES = {
    "1Y":  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_1Y",
    "2Y":  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",
    "5Y":  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_5Y",
    "10Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",
    "20Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_20Y",
    "30Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y",
}

def _ecb_yc_full(series_key: str, start: str = "2004-01-01") -> pd.Series:
    resp = requests.get(
        f"{ECB_YC_URL}/{series_key}",
        params={"format": "csvdata", "startPeriod": start, "endPeriod": TODAY},
        headers={"Accept": "text/csv"},
        timeout=60,
    )
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    if df.empty or "TIME_PERIOD" not in df.columns:
        return pd.Series(dtype=float)
    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])
    df = df.dropna(subset=["OBS_VALUE"])
    return df.set_index("TIME_PERIOD")["OBS_VALUE"].astype(float)

def fetch_germany_yields() -> list:
    print("[Germany] fetching full history from ECB YC API...")
    rows = []
    for maturity, key in GERMANY_YC_SERIES.items():
        print(f"  {maturity}...")
        try:
            series = _ecb_yc_full(key)
            for date, value in series.items():
                rows.append({
                    "country":          "Germany",
                    "source":           "ECB",
                    "maturity":         maturity,
                    "observation_date": date.date().isoformat(),
                    "yield_pct":        round(float(value), 4),
                    "frequency":        "daily",
                })
            time.sleep(0.5)
        except Exception as exc:
            print(f"  ERROR {maturity}: {exc}")
    print(f"  {len(rows)} rows")
    return rows


# ── France / Italy / Spain — ECB IRS dataflow (monthly, 10Y only) ────────────
ECB_IRS_URL = "https://data-api.ecb.europa.eu/service/data/IRS"
ECB_IRS_SERIES = {
    "France": {"10Y": "M.FR.L.L40.CI.0000.EUR.N.Z"},
    "Italy":  {"10Y": "M.IT.L.L40.CI.0000.EUR.N.Z"},
    "Spain":  {"10Y": "M.ES.L.L40.CI.0000.EUR.N.Z"},
}

def _ecb_irs_full(series_key: str, start: str = "1993-01-01") -> pd.Series:
    resp = requests.get(
        f"{ECB_IRS_URL}/{series_key}",
        params={"format": "csvdata", "startPeriod": start, "endPeriod": TODAY},
        headers={"Accept": "text/csv"},
        timeout=60,
    )
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    if df.empty or "TIME_PERIOD" not in df.columns:
        return pd.Series(dtype=float)
    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])
    df = df.dropna(subset=["OBS_VALUE"])
    return df.set_index("TIME_PERIOD")["OBS_VALUE"].astype(float)

def fetch_ecb_irs_yields(country: str) -> list:
    print(f"[{country}] fetching full history from ECB IRS API...")
    rows = []
    for maturity, key in ECB_IRS_SERIES[country].items():
        print(f"  {maturity}...")
        try:
            series = _ecb_irs_full(key)
            for date, value in series.items():
                rows.append({
                    "country":          country,
                    "source":           "ECB",
                    "maturity":         maturity,
                    "observation_date": date.date().isoformat(),
                    "yield_pct":        round(float(value), 4),
                    "frequency":        "monthly",
                })
            time.sleep(0.3)
        except Exception as exc:
            print(f"  ERROR {maturity}: {exc}")
    print(f"  {len(rows)} rows")
    return rows


# ── Canada — Bank of Canada Valet API ────────────────────────────────────────
BOC_URL = "https://www.bankofcanada.ca/valet/observations"
CANADA_SERIES = {
    "2Y":  "BD.CDN.2YR.DQ.YLD",
    "3Y":  "BD.CDN.3YR.DQ.YLD",
    "5Y":  "BD.CDN.5YR.DQ.YLD",
    "7Y":  "BD.CDN.7YR.DQ.YLD",
    "10Y": "BD.CDN.10YR.DQ.YLD",
}

def fetch_canada_yields() -> list:
    print("[Canada] fetching full history from Bank of Canada Valet...")
    rows = []
    for maturity, series_id in CANADA_SERIES.items():
        print(f"  {maturity}...")
        try:
            resp = requests.get(
                f"{BOC_URL}/{series_id}/json",
                params={"start_date": "1990-01-01", "end_date": TODAY},
                timeout=60,
            )
            resp.raise_for_status()
            for obs in resp.json().get("observations", []):
                raw = obs.get(series_id, {}).get("v")
                if raw is None:
                    continue
                rows.append({
                    "country":          "Canada",
                    "source":           "BoC",
                    "maturity":         maturity,
                    "observation_date": obs["d"],
                    "yield_pct":        round(float(raw), 4),
                    "frequency":        "daily",
                })
        except Exception as exc:
            print(f"  ERROR {maturity}: {exc}")
    print(f"  {len(rows)} rows")
    return rows


# ── Switzerland — SNB rendoblid cube API ─────────────────────────────────────
SNB_CUBE_URL = "https://data.snb.ch/api/cube/rendoblid/data/json/en"
SWITZERLAND_SERIES = {
    "1Y":  "1J",
    "2Y":  "2J",
    "5Y":  "5J",
    "10Y": "10J0",
    "20Y": "20J",
    "30Y": "30J",
}

def fetch_switzerland_yields() -> list:
    print("[Switzerland] fetching full history from SNB cube...")
    try:
        resp = requests.get(
            SNB_CUBE_URL,
            params={"fromDate": "2001-01-01", "toDate": TODAY},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return []

    series_by_key: dict = {}
    for ts in data.get("timeseries", []):
        key = ts["metadata"]["key"]
        if "{" not in key or not key.endswith("}"):
            continue
        fragment = key[key.index("{") + 1 : -1]
        series_by_key[fragment] = [
            (v["date"], float(v["value"]))
            for v in ts.get("values", [])
            if v.get("value") is not None
        ]

    rows = []
    for maturity, fragment in SWITZERLAND_SERIES.items():
        for date_str, value in series_by_key.get(fragment, []):
            rows.append({
                "country":          "Switzerland",
                "source":           "SNB",
                "maturity":         maturity,
                "observation_date": date_str,
                "yield_pct":        round(value, 4),
                "frequency":        "monthly",
            })
    print(f"  {len(rows)} rows")
    return rows


# ── Japan — MOF jgbcm_all.csv (full history from 1974) ──────────────────────
JGB_CSV_URL  = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
JAPAN_COLS   = {0: "1Y", 1: "2Y", 2: "3Y", 4: "5Y", 6: "7Y", 9: "10Y", 12: "20Y", 13: "30Y", 14: "40Y"}
ERA_BASE     = {"S": 1925, "H": 1988, "R": 2018}
ERA_RE       = re.compile(r"^([SHR])(\d+)\.(\d+)\.(\d+)$")

def _parse_era(raw: str):
    m = ERA_RE.match(raw.strip())
    if not m:
        return None
    era, yr, mo, day = m.groups()
    return f"{ERA_BASE[era] + int(yr):04d}-{int(mo):02d}-{int(day):02d}"

def fetch_japan_yields() -> list:
    print("[Japan] fetching full history from MOF jgbcm_all.csv...")
    try:
        resp = requests.get(JGB_CSV_URL, timeout=30)
        resp.raise_for_status()
        text = resp.content.decode("shift_jis")
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return []

    rows = []
    for line in text.splitlines()[2:]:   # skip two header rows
        fields = line.strip().split(",")
        if len(fields) < 16:
            continue
        date_str = _parse_era(fields[0])
        if date_str is None:
            continue
        for col_idx, maturity in JAPAN_COLS.items():
            raw = fields[col_idx + 1].strip()   # +1 because fields[0] is the date
            if raw in ("", "-"):
                continue
            try:
                rows.append({
                    "country":          "Japan",
                    "source":           "MOF",
                    "maturity":         maturity,
                    "observation_date": date_str,
                    "yield_pct":        round(float(raw), 4),
                    "frequency":        "daily",
                })
            except ValueError:
                pass
    print(f"  {len(rows)} rows")
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# SPREAD FETCHERS
# ═══════════════════════════════════════════════════════════════════════════

# ── US spread — FRED T10Y2Y ──────────────────────────────────────────────────
def fetch_us_spread() -> list:
    print("[US spread] fetching T10Y2Y from FRED...")
    fred   = Fred(api_key=FRED_API_KEY)
    series = fred.get_series("T10Y2Y", observation_start="1976-06-01").dropna()
    rows   = [
        {
            "country":          "US",
            "source":           "FRED",
            "observation_date": d.date().isoformat(),
            "spread_pct":       round(float(v), 4),
        }
        for d, v in series.items()
    ]
    print(f"  {len(rows)} rows")
    return rows


# ── UK spread — derived from BoE workbooks (10Y − 2Y) ───────────────────────
def fetch_uk_spread() -> list:
    print("[UK spread] computing from BoE workbooks...")
    try:
        zb = _boe_zip()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return []
    with zipfile.ZipFile(BytesIO(zb)) as z:
        excel_files = sorted(f for f in z.namelist() if f.endswith(".xlsx"))

    frames = []
    for fname in excel_files:
        try:
            maturity_row, data_rows = _parse_boe_workbook(zb, fname)
        except Exception:
            continue
        c2  = _best_col(maturity_row, 2.0)
        c10 = _best_col(maturity_row, 10.0)
        if c2 is None or c10 is None:
            continue
        frame = pd.DataFrame({
            "2Y":  pd.to_numeric(data_rows[c2],  errors="coerce"),
            "10Y": pd.to_numeric(data_rows[c10], errors="coerce"),
        }, index=data_rows.index).dropna()
        frames.append(frame)

    if not frames:
        return []
    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    spread   = combined["10Y"] - combined["2Y"]
    rows     = [
        {
            "country":          "UK",
            "source":           "BoE",
            "observation_date": d.date().isoformat(),
            "spread_pct":       round(float(v), 4),
        }
        for d, v in spread.items()
    ]
    print(f"  {len(rows)} rows")
    return rows


# ── Germany spread — Bundesbank BBSIS (genuine Bund 2Y + 10Y) ───────────────
BBK_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSIS"
BBK_SERIES = {
    "2Y":  "D.I.ZAR.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A",
    "10Y": "D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A",
}

def _parse_bbk_json(payload: dict) -> dict:
    data        = payload["data"]
    dates       = [v["id"] for v in data["structure"]["dimensions"]["observation"][0]["values"]]
    series      = data["dataSets"][0]["series"]
    if not series:
        return {}
    observations = next(iter(series.values()))["observations"]
    out = {}
    for pos, entry in observations.items():
        val = entry[0] if entry else None
        if val is not None:
            out[dates[int(pos)]] = float(val)
    return out

def _bbk_fetch(label: str) -> dict:
    cache = CACHE_DIR / f"bbk_{label}.pkl"
    if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    print(f"  downloading Bundesbank {label} series...")
    resp = requests.get(
        f"{BBK_URL}/{BBK_SERIES[label]}",
        params={"startPeriod": "1997-01-01", "format": "json"},
        timeout=120,
    )
    resp.raise_for_status()
    parsed = _parse_bbk_json(resp.json())
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as fh:
        pickle.dump(parsed, fh)
    return parsed

def fetch_germany_spread() -> list:
    print("[Germany spread] fetching from Bundesbank BBSIS...")
    try:
        two = _bbk_fetch("2Y")
        ten = _bbk_fetch("10Y")
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return []
    both = sorted(set(two) & set(ten))
    rows = [
        {
            "country":          "Germany",
            "source":           "Bundesbank",
            "observation_date": d,
            "spread_pct":       round(ten[d] - two[d], 4),
        }
        for d in both
    ]
    print(f"  {len(rows)} rows")
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main() -> None:
    print("=" * 64)
    print("Yield Curve Visualiser — Supabase seed")
    print(f"Target: {SUPABASE_URL}")
    print(f"Date:   {TODAY}")
    print("=" * 64)

    # ── Yield curves ─────────────────────────────────────────────────────────
    print("\n▸ YIELD CURVES  →  yield_observations\n")
    yield_fetchers = [
        fetch_us_yields,
        fetch_uk_yields,
        fetch_germany_yields,
        lambda: fetch_ecb_irs_yields("France"),
        lambda: fetch_ecb_irs_yields("Italy"),
        lambda: fetch_ecb_irs_yields("Spain"),
        fetch_canada_yields,
        fetch_switzerland_yields,
        fetch_japan_yields,
    ]
    for fetcher in yield_fetchers:
        try:
            rows = fetcher()
            upsert_rows("yield_observations", rows)
        except Exception as exc:
            print(f"  FATAL: {exc}")
        print()

    # ── Spreads ───────────────────────────────────────────────────────────────
    print("\n▸ SPREADS  →  spread_observations\n")
    spread_fetchers = [
        fetch_us_spread,
        fetch_uk_spread,
        fetch_germany_spread,
    ]
    for fetcher in spread_fetchers:
        try:
            rows = fetcher()
            upsert_rows("spread_observations", rows)
        except Exception as exc:
            print(f"  FATAL: {exc}")
        print()

    print("Seed complete.")


if __name__ == "__main__":
    main()
