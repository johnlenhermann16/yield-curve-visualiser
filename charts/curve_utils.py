# charts/curve_utils.py
#
# Shared, plotting-library-agnostic helpers for working with yield curves.
# Both the matplotlib chart (plot_curves.py) and the Plotly chart
# (plot_curves_plotly.py) import from here so the two chart implementations
# never need to share code with each other directly.

# Colour scheme — each country gets its own colour, assigned in a fixed
# order from a colourblind-validated categorical palette. Validated as a
# full 9-colour set with the dataviz skill's validator
# (scripts/validate_palette.js, --mode light, adjacent-pairs gate — the
# right gate for a multi-line chart): all hard gates (lightness, chroma,
# CVD separation, normal-vision floor) pass. Two soft WARNs remain (the
# aqua/magenta adjacent pair sits in the legal-with-secondary-encoding 6-8
# CVD band, and three slots dip under 3:1 surface contrast) — both are
# covered by this chart's existing legend + hover-tooltip labelling, so
# identity is never carried by colour alone.
COUNTRY_COLOURS = {
    "US": "#2a78d6",           # blue
    "UK": "#eb6834",           # orange
    "Germany": "#4a3aa7",      # violet
    "Spain": "#eda100",        # yellow
    "France": "#e34948",       # red
    "Italy": "#008300",        # green
    "Canada": "#e87ba4",       # magenta
    "Switzerland": "#a15c2e",  # brown
    "Japan": "#1a9c8f",        # teal — #c0392b (deep red, flag-matching) was
                               # tried first but fails the palette validator:
                               # ΔE 8.4 (normal vision, below the 15 floor) and
                               # ΔE 0.8 (deutan) against Switzerland's brown,
                               # i.e. genuinely hard to tell apart, not a soft
                               # warning. Teal passes every check cleanly.
}

# Default colour if we add a new country we haven't assigned yet
DEFAULT_COLOUR = "#5a5a5a"  # neutral grey — distinct from every slot above

# Countries whose fetcher can only return a single "10Y" point (the real
# per-country ECB series is a monthly single-maturity convergence rate, not
# a full spot curve — see data/fetch_france.py for the full explanation).
# Shared between app.py (UI labelling, excluding them from curve-shape
# analysis) and plot_curves_plotly.py (rendering them as a lone marker
# instead of a line).
SINGLE_MATURITY_ONLY = {"France", "Italy", "Spain"}

# A spread smaller than this (in percentage points) counts as "flat"
# rather than clearly normal or inverted.
FLAT_THRESHOLD_PP = 0.1


def maturity_to_years(label):
    """
    Convert a maturity label like "3M" or "10Y" into a number of years.
    This is used to sort maturities in the right order (shortest to longest).

    Examples:
        "3M"  → 0.25
        "1Y"  → 1.0
        "10Y" → 10.0
    """
    label = label.strip()
    if label.endswith("M"):
        return int(label[:-1]) / 12
    elif label.endswith("Y"):
        return int(label[:-1])
    else:
        raise ValueError(f"Unrecognised maturity format: '{label}'")


def find_inversion_zones(x_values, y_values):
    """
    Look for spots where a yield is HIGHER than the next longer maturity.
    That's an inversion — short-term rates exceed long-term rates.

    Returns a list of (x_start, x_end) pairs marking inverted segments.
    """
    zones = []
    for i in range(len(y_values) - 1):
        if y_values[i] > y_values[i + 1]:
            zones.append((x_values[i], x_values[i + 1]))
    return zones


def get_all_maturities(all_yields_dict):
    """
    Given a dictionary of {country: pd.Series of yields},
    find ALL unique maturities across every country, sorted short-to-long.

    We need this so the x-axis can show every maturity that exists in any dataset.

    Example: US has 1M, 3M, 6M, 1Y, 2Y... 30Y
             UK has         2Y, 5Y, 10Y, 20Y, 30Y
             Combined x-axis: 1M, 3M, 6M, 1Y, 2Y, 5Y, 10Y, 20Y, 30Y
    """
    all_maturities = set()
    for yields in all_yields_dict.values():
        all_maturities.update(yields.index)

    # Sort by number of years so they appear in the right order
    return sorted(all_maturities, key=maturity_to_years)


def classify_curve(yields):
    """
    Classify a single country's yield curve as "normal", "inverted" or
    "flat", based on the spread between its shortest and longest available
    maturities, and produce a short plain-English explanation.

    Parameters:
    -----------
    yields : pd.Series
        Yields for one country, indexed by maturity label (e.g. "1Y", "10Y").

    Returns:
    --------
    dict with keys: short_label, short_yield, long_label, long_yield,
    spread, classification, explanation. Returns None if there isn't
    enough data (fewer than 2 maturities) to classify.
    """
    if yields is None or len(yields) < 2:
        return None

    sorted_maturities = sorted(yields.index, key=maturity_to_years)
    short_label = sorted_maturities[0]
    long_label = sorted_maturities[-1]
    short_yield = float(yields[short_label])
    long_yield = float(yields[long_label])
    spread = long_yield - short_yield

    if abs(spread) <= FLAT_THRESHOLD_PP:
        classification = "flat"
        explanation = (
            f"The curve is roughly flat: the {short_label} yield "
            f"({short_yield:.2f}%) and the {long_label} yield ({long_yield:.2f}%) "
            f"are within {FLAT_THRESHOLD_PP:.1f}pp of each other. A flat curve "
            f"often shows up during a transition, when investors are unsure "
            f"whether growth or a slowdown lies ahead."
        )
    elif spread > 0:
        classification = "normal"
        explanation = (
            f"The curve is normal (upward-sloping): the {long_label} yield "
            f"({long_yield:.2f}%) is {spread:.2f}pp above the {short_label} yield "
            f"({short_yield:.2f}%). This is the typical shape, reflecting the "
            f"extra compensation investors demand for lending over a longer horizon."
        )
    else:
        classification = "inverted"
        explanation = (
            f"The curve is inverted: the {short_label} yield ({short_yield:.2f}%) "
            f"is {abs(spread):.2f}pp above the {long_label} yield ({long_yield:.2f}%). "
            f"Inversions like this have historically preceded economic slowdowns, "
            f"as they suggest investors expect rates (and growth) to fall."
        )

    return {
        "short_label": short_label,
        "short_yield": short_yield,
        "long_label": long_label,
        "long_yield": long_yield,
        "spread": spread,
        "classification": classification,
        "explanation": explanation,
    }
