# data/countries.py
#
# Single source of truth mapping a country name to its fetch function.
# To add a new country, add one entry here — every UI and chart that
# iterates over COUNTRY_FETCHERS (e.g. app.py) picks it up automatically.

from data.fetch_us import get_us_yields
from data.fetch_uk import get_uk_yields
from data.fetch_germany import get_germany_yields
from data.fetch_france import get_france_yields
from data.fetch_italy import get_italy_yields
from data.fetch_spain import get_spain_yields
from data.fetch_canada import get_canada_yields
from data.fetch_switzerland import get_switzerland_yields
from data.fetch_japan import get_japan_yields

# Australia (data/fetch_australia.py) is intentionally NOT registered here —
# the only available series is a single monthly "10Y" point (see that
# file's docstring), which isn't useful enough for a yield curve visualiser.
# The fetch file is kept in case a real multi-maturity source turns up
# later; it's just unplugged from the UI for now.

COUNTRY_FETCHERS = {
    "US": get_us_yields,
    "UK": get_uk_yields,
    "Germany": get_germany_yields,
    "France": get_france_yields,
    "Italy": get_italy_yields,
    "Spain": get_spain_yields,
    "Canada": get_canada_yields,
    "Switzerland": get_switzerland_yields,
    "Japan": get_japan_yields,
}
