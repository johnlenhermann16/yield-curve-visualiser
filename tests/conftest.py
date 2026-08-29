import os

# Several modules read these at import time (api/main.py, data/fetch_us.py,
# seed_supabase.py) and raise KeyError if unset. Set harmless dummy values so
# importing the app in tests never needs a real .env — every network call
# these keys would gate is mocked in the tests themselves.
os.environ.setdefault("FRED_API_KEY", "test-fred-key")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_KEY", "test-supabase-key")
