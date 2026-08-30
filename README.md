# Yield Curve Visualiser

Interactive government bond yield curves and 2Y10Y spreads for nine
countries (US, UK, Germany, France, Italy, Spain, Canada, Switzerland,
Japan), pulled from each country's own central bank / statistical source.

**Live app:** https://yield-curve-react.vercel.app

## How it fits together

This repo is the **data side**: per-country fetch modules, a FastAPI
wrapper around them for local development, and a one-shot script that
seeds Supabase. The deployed app itself is a separate repo,
[yield-curve-react](https://github.com/johnlenhermann16/yield-curve-react),
which reads directly from Supabase and does not call this backend.

```
data/fetch_*.py  →  seed_supabase.py  →  Supabase (Postgres)  →  yield-curve-react (Vercel)
                                             ^
                              api/main.py reads the same fetchers
                              directly, for local dev only — not deployed
```

- **Supabase** is the shared source of truth: tables `yield_observations`
  and `spread_observations`, populated by running `seed_supabase.py`
  whenever a fetch module changes.
- **api/main.py** (FastAPI) is a thin HTTP layer over the same fetch
  modules, useful for testing a fetcher without running the whole seeding
  script. It is not deployed anywhere; the frontend never calls it.
- **yield-curve-react** is the only thing end users see, and reads
  Supabase directly via PostgREST — see that repo for frontend setup.

## Repo layout

```
api/main.py         FastAPI app — local dev / testing only, not deployed
data/                Per-country fetch modules + the COUNTRY_FETCHERS registry
charts/              Chart-building code used by the legacy scripts below
main.py              Legacy: fetches one date, draws a static matplotlib chart
app.py               Legacy: interactive Streamlit prototype, superseded by yield-curve-react
seed_supabase.py     One-shot seeder: runs every fetcher, upserts into Supabase
design/              Design-canvas sources for the frontend's visual design
docs/                Architecture, per-country data status, known issues, roadmap
```

`main.py` and `app.py` predate the FastAPI + React setup and aren't
maintained as the primary interface, but they still run against the same
fetch modules if you want a quick local chart without the rest of the
stack.

## Data sources

| Country | Source | Coverage |
|---|---|---|
| US | FRED | Full curve (1M–30Y) |
| UK | Bank of England | Full curve |
| Germany | ECB euro-area AAA composite (curve) / Bundesbank (spread) | Full curve, but see caveat below |
| France, Italy, Spain | ECB | 10Y only |
| Canada, Switzerland, Japan | — | Full curve; no spread data yet — correctness not independently re-verified this session |

**Known data caveats:**
- Germany's full-curve endpoint currently uses the ECB's euro-area AAA
  composite as a stand-in, which has been confirmed off by up to +71bp
  against real German bunds during stress periods (e.g. the 2012 euro
  crisis). The separate 2Y10Y spread endpoint for Germany uses real
  Bundesbank data and is correct. Fixing the full-curve fetch to also use
  Bundesbank is tracked in `docs/roadmap.md`.
- That same Bundesbank source (the correct one, used for the Germany
  spread) is a legacy SDMX API with an uncertain long-term future — its
  own documentation page currently 404s, suggesting a migration or
  retirement is underway, with no confirmed shutdown date.
- Canada, Switzerland, and Japan curve data hasn't been independently
  re-verified for correctness since it was first added — treat it with
  the same caution as an unaudited data source until confirmed.

Details on every other data-source quirk are in `docs/landmines.md`.

## Setup

Requires Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in FRED_API_KEY, SUPABASE_URL, SUPABASE_KEY
```

Run the backend (local dev only, not required to use the live app):
```bash
uvicorn api.main:app --reload
```

Run the legacy Streamlit prototype:
```bash
streamlit run app.py
```

Re-seed Supabase after a fetch-module change:
```bash
python seed_supabase.py
```

Frontend setup lives in the
[yield-curve-react](https://github.com/johnlenhermann16/yield-curve-react)
repo.

## Documentation

- `docs/architecture.md` — full project structure, both repos, tech stack
- `docs/local-dev.md` — running everything locally, required credentials
- `docs/countries.md` — per-country data source status
- `docs/spread-chart.md` — 2Y10Y spread feature status per country
- `docs/landmines.md` — known bugs/gotchas in the data sources and frontend
- `docs/roadmap.md` — current state, known issues, what's not done yet
- `CLAUDE.md` — project conventions for AI-assisted development in this repo

## License

MIT — see [LICENSE](LICENSE).
