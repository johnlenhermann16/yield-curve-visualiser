"""
Minimal smoke tests: one per data/fetch_*.py entry function. Each mocks the
network call (or, for UK/Germany-spread, the on-disk-caching helper one
layer in — see below) with a small canned payload and asserts the function
returns its documented (actual_date, pd.Series) / list-of-dicts shape without
raising. Not a correctness suite for the parsing logic itself.

fetch_australia.py is skipped — it's intentionally unplugged from
COUNTRY_FETCHERS (see data/countries.py) and unused by the app.
"""

import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pandas as pd


def _csv_response(text):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.text = text
    return resp


def test_get_us_yields_shape():
    from data.fetch_us import US_SERIES, get_us_yields

    canned = pd.Series({pd.Timestamp("2023-01-13"): 4.5})
    with patch("data.fetch_us.Fred") as MockFred:
        MockFred.return_value.get_series.return_value = canned
        actual_date, yields = get_us_yields("2023-01-13")

    assert actual_date == "2023-01-13"
    assert set(yields.index) == set(US_SERIES.keys())


def _fake_boe_zip_bytes():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("GLC Nominal daily data_2016 to present.xlsx", b"")
    return buf.getvalue()


def test_get_uk_yields_shape():
    from data.fetch_uk import get_uk_yields

    maturity_row = pd.Series({0: None, 1: 2.0, 2: 5.0, 3: 10.0, 4: 20.0, 5: 30.0})
    data_rows = pd.DataFrame(
        {1: [4.1], 2: [4.2], 3: [4.3], 4: [4.4], 5: [4.5]},
        index=[pd.Timestamp("2023-01-13")],
    )
    with patch("data.fetch_uk._get_boe_zip_bytes", return_value=_fake_boe_zip_bytes()), \
         patch("data.fetch_uk._get_parsed_workbook", return_value=(maturity_row, data_rows)):
        actual_date, yields = get_uk_yields("2023-01-13")

    assert actual_date == "2023-01-13"
    assert set(yields.index) == {"2Y", "5Y", "10Y", "20Y", "30Y"}


def test_get_uk_spread_series_shape():
    from data.fetch_uk import get_uk_spread_series

    frame = pd.DataFrame(
        {"2Y": [4.0, 4.1], "10Y": [4.5, 4.6]},
        index=[pd.Timestamp("2023-01-10"), pd.Timestamp("2023-01-13")],
    )
    with patch("data.fetch_uk._get_boe_zip_bytes", return_value=_fake_boe_zip_bytes()), \
         patch("data.fetch_uk._workbook_spread_frame", return_value=frame):
        data = get_uk_spread_series("2023-01-01", "2023-01-31")

    assert data == [
        {"date": "2023-01-10", "spread": 0.5},
        {"date": "2023-01-13", "spread": 0.5},
    ]


def test_get_canada_yields_shape():
    from data.fetch_canada import CANADA_SERIES, get_canada_yields

    def fake_get(url, params=None, timeout=None):
        series_id = url.rsplit("/", 2)[-2]
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "observations": [{"d": "2023-01-13", series_id: {"v": "4.0"}}]
        }
        return resp

    with patch("data.fetch_canada.requests.get", side_effect=fake_get):
        actual_date, yields = get_canada_yields("2023-01-13")

    assert actual_date == "2023-01-13"
    assert set(yields.index) == set(CANADA_SERIES.keys())


def test_get_italy_yields_shape():
    from data.fetch_italy import get_italy_yields

    with patch("data.fetch_italy.requests.get", return_value=_csv_response(
        "TIME_PERIOD,OBS_VALUE\n2023-01-15,4.2\n"
    )):
        actual_date, yields = get_italy_yields("2023-01-13")

    assert actual_date == "2023-01-15"
    assert yields.to_dict() == {"10Y": 4.2}


def test_get_spain_yields_shape():
    from data.fetch_spain import get_spain_yields

    with patch("data.fetch_spain.requests.get", return_value=_csv_response(
        "TIME_PERIOD,OBS_VALUE\n2023-01-15,3.9\n"
    )):
        actual_date, yields = get_spain_yields("2023-01-13")

    assert actual_date == "2023-01-15"
    assert yields.to_dict() == {"10Y": 3.9}


def test_get_france_yields_shape():
    from data.fetch_france import get_france_yields

    with patch("data.fetch_france.requests.get", return_value=_csv_response(
        "TIME_PERIOD,OBS_VALUE\n2023-01-15,2.8\n"
    )):
        actual_date, yields = get_france_yields("2023-01-13")

    assert actual_date == "2023-01-15"
    assert yields.to_dict() == {"10Y": 2.8}


def test_get_switzerland_yields_shape():
    from data.fetch_switzerland import SWITZERLAND_SERIES, get_switzerland_yields

    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "timeseries": [
            {
                "metadata": {"key": f"EPB@SNB.rendoblid{{{frag}}}"},
                "values": [{"date": "2023-01-13", "value": "4.0"}],
            }
            for frag in SWITZERLAND_SERIES.values()
        ]
    }
    with patch("data.fetch_switzerland.requests.get", return_value=resp):
        actual_date, yields = get_switzerland_yields("2023-01-13")

    assert actual_date == "2023-01-13"
    assert set(yields.index) == set(SWITZERLAND_SERIES.keys())


def test_get_germany_yields_shape():
    from data.fetch_germany import GERMANY_SERIES, get_germany_yields

    with patch("data.fetch_germany.requests.get", return_value=_csv_response(
        "TIME_PERIOD,OBS_VALUE\n2023-01-15,3.0\n"
    )):
        actual_date, yields = get_germany_yields("2023-01-13")

    assert actual_date == "2023-01-15"
    assert set(yields.index) == set(GERMANY_SERIES.keys())


def test_get_germany_spread_series_shape():
    from data.fetch_germany_spread import get_germany_spread_series

    canned = {
        "2Y": {"2023-01-10": 3.0, "2023-01-13": 3.1},
        "10Y": {"2023-01-10": 3.5, "2023-01-13": 3.6},
    }
    with patch(
        "data.fetch_germany_spread._fetch_series",
        side_effect=lambda label: canned[label],
    ):
        data = get_germany_spread_series("2023-01-01", "2023-01-31")

    assert data == [
        {"date": "2023-01-10", "spread": 0.5},
        {"date": "2023-01-13", "spread": 0.5},
    ]


def test_get_japan_yields_shape():
    from data.fetch_japan import JAPAN_COLUMNS, get_japan_yields

    row = "R5.1.13," + ",".join(["4.0"] * 15) + "\n"
    csv_bytes = ("header line 1\nheader line 2\n" + row).encode("shift_jis")
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.content = csv_bytes
    with patch("data.fetch_japan.requests.get", return_value=resp):
        actual_date, yields = get_japan_yields("2023-01-13")

    assert actual_date == "2023-01-13"
    assert set(yields.index) == set(JAPAN_COLUMNS.values())
