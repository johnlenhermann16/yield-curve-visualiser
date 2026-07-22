# main.py

from data.fetch_us import get_us_yields
from data.fetch_uk import get_uk_yields
from data.fetch_germany import get_germany_yields
from charts.plot_curves import plot_yield_curves

# The date we want to visualise
DATE = "2023-01-13"

# Each fetch function returns (actual_date, yields): actual_date is the
# nearest trading day the data actually came from (it can differ from DATE
# on a weekend/holiday), yields is a pd.Series indexed by maturity label.

# --- Fetch US yields ---
print(f"Fetching US yields for {DATE}...")
us_actual_date, us_yields = get_us_yields(DATE)
print(f"US data fetched (actual date used: {us_actual_date}):\n", us_yields, "\n")

# --- Fetch UK yields ---
print(f"Fetching UK yields for {DATE}...")
uk_actual_date, uk_yields = get_uk_yields(DATE)
print(f"UK data fetched (actual date used: {uk_actual_date}):\n", uk_yields, "\n")

# --- Fetch Germany yields ---
print(f"Fetching Germany yields for {DATE}...")
germany_actual_date, germany_yields = get_germany_yields(DATE)
print(f"Germany data fetched (actual date used: {germany_actual_date}):\n", germany_yields, "\n")

# --- Draw the combined chart ---
# We pass a dictionary: country name → its yields Series
print("Drawing combined chart...")
plot_yield_curves(
    all_yields_dict={
        "US": us_yields,
        "UK": uk_yields,
        "Germany": germany_yields,
    },
    date=DATE
)
