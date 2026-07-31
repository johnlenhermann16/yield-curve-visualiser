# Local Dev Setup

- Backend: activate venv first (`.venv\Scripts\Activate.ps1` on
  PowerShell — NOT `source`, this is Windows), then
  `uvicorn api.main:app --reload` (port 8000)
- Frontend: separate terminal, `cd D:\yield-curve-react && npm run dev`
  (port 5173) — must stay running simultaneously with backend, in its
  own terminal, untouched
- D:\yield-curve-react\.env.local must contain
  VITE_API_URL=http://localhost:8000 for local dev — if this file is
  ever deleted/missing, the frontend silently falls back to hitting
  the production Railway URL instead, causing confusing partial
  failures (e.g. endpoints that exist locally but not yet deployed
  will 400)

## Credentials
- FRED API key: ***REMOVED***
