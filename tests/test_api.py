"""
Minimal smoke tests: one per route in api/main.py, against a TestClient.
Fetchers are mocked so no real network call happens.
"""

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_countries():
    resp = client.get("/api/countries")
    assert resp.status_code == 200
    assert "US" in resp.json()["countries"]


def test_yields():
    canned = ("2023-01-13", pd.Series({"10Y": 4.0}))
    with patch.dict("api.main.COUNTRY_FETCHERS", {"US": lambda date: canned}):
        resp = client.get("/api/yields", params={"countries": "US", "date": "2023-01-13"})

    assert resp.status_code == 200
    body = resp.json()["countries"]["US"]
    assert body == {"actual_date": "2023-01-13", "yields": {"10Y": 4.0}, "error": None}


def test_spread_uk():
    with patch(
        "api.main.get_uk_spread_series",
        return_value=[{"date": "2023-01-13", "spread": 0.5}],
    ):
        resp = client.get("/api/spread", params={"country": "UK"})

    assert resp.status_code == 200
    assert resp.json()["data"] == [{"date": "2023-01-13", "spread": 0.5}]


def test_spread_germany():
    with patch(
        "api.main.get_germany_spread_series",
        return_value=[{"date": "2023-01-13", "spread": 0.3}],
    ):
        resp = client.get("/api/spread", params={"country": "Germany"})

    assert resp.status_code == 200
    assert resp.json()["data"] == [{"date": "2023-01-13", "spread": 0.3}]


def test_spread_us():
    canned_series = pd.Series({pd.Timestamp("2023-01-13"): 0.7})
    with patch("api.main.Fred") as MockFred:
        MockFred.return_value.get_series.return_value = canned_series
        resp = client.get("/api/spread", params={"country": "US"})

    assert resp.status_code == 200
    assert resp.json()["data"] == [{"date": "2023-01-13", "spread": 0.7}]


def test_historical_context():
    resp = client.get("/api/historical-context", params={"date": "2020-05-01"})
    assert resp.status_code == 200
    assert resp.json()["title"].startswith("2020")
