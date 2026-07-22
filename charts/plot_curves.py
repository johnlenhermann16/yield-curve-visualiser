# charts/plot_curves.py
#
# Matplotlib rendering only. Shared, non-plotting logic (maturity sorting,
# inversion detection, colours) lives in curve_utils.py — see
# plot_curves_plotly.py for the Plotly equivalent of this chart.

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from charts.curve_utils import (
    COUNTRY_COLOURS,
    DEFAULT_COLOUR,
    find_inversion_zones,
    get_all_maturities,
    maturity_to_years,
)

# Chart chrome — light surface with muted ink tones so the data (not the
# frame) carries the emphasis.
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"


def plot_yield_curves(all_yields_dict, date):
    """
    Plot yield curves for one or more countries on the same chart.

    Parameters:
    -----------
    all_yields_dict : dict
        A dictionary where keys are country names (e.g. "US", "UK")
        and values are pandas Series of yields indexed by maturity label.

        Example:
        {
            "US": pd.Series({"1Y": 4.5, "2Y": 4.7, "10Y": 3.9}),
            "UK": pd.Series({"2Y": 3.8, "10Y": 4.1}),
        }

    date : str
        The date to show in the chart title, e.g. "2023-01-13"
    """

    # Get the combined list of all maturities across all countries
    all_maturities = get_all_maturities(all_yields_dict)

    # Assign a numeric x-position to each maturity label (0, 1, 2, 3...)
    # We'll use these as the positions on the x-axis
    maturity_positions = {m: i for i, m in enumerate(all_maturities)}

    # Create the figure and axes
    # figsize=(14, 6) makes it wider than tall — good for yield curves
    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # Recessive frame — drop the top/right box, keep a hairline baseline
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)

    # We'll collect all legend entries in this list
    legend_handles = []

    # Track whether any country has inversions (for the legend)
    any_inversions = False

    # Loop over each country and draw its yield curve
    for country, yields in all_yields_dict.items():

        if yields.empty:
            print(f"Skipping {country}: no yield data to plot")
            continue

        # Get the colour for this country (or use purple as a fallback)
        colour = COUNTRY_COLOURS.get(country, DEFAULT_COLOUR)

        # Sort this country's maturities in order (shortest to longest)
        sorted_maturities = sorted(yields.index, key=maturity_to_years)

        # Get the x positions for just this country's maturities
        # (some maturities might only exist in US, not UK, etc.)
        x_positions = [maturity_positions[m] for m in sorted_maturities]

        # Get the yield values in the same order
        y_yields = [yields[m] for m in sorted_maturities]

        # Draw the line
        line, = ax.plot(
            x_positions,
            y_yields,
            color=colour,
            linewidth=2,
            marker="o",
            markersize=8,
            markeredgecolor=SURFACE,   # surface ring so markers stay legible on overlap
            markeredgewidth=1.5,
            label=f"{country} ({date})",
            zorder=3
        )

        # Detect inversions for this country
        inversion_zones = find_inversion_zones(x_positions, y_yields)

        if inversion_zones:
            any_inversions = True
            for (x_start, x_end) in inversion_zones:
                ax.axvspan(
                    x_start, x_end,
                    alpha=0.12,
                    color=colour,   # use the country's colour for its inversion
                    zorder=1
                )

        # Add this country's line to the legend
        legend_handles.append(line)

    # If any country had an inversion, add one legend entry explaining it
    if any_inversions:
        inversion_patch = mpatches.Patch(
            color="grey",
            alpha=0.4,
            label="Inversion zone (short > long)"
        )
        legend_handles.append(inversion_patch)

    # Set up the x-axis labels
    ax.set_xticks(list(range(len(all_maturities))))
    ax.set_xticklabels(all_maturities, fontsize=9, color=TEXT_MUTED)
    ax.tick_params(axis="y", colors=TEXT_MUTED, labelsize=9)
    ax.tick_params(axis="x", colors=BASELINE)

    # Labels and title
    ax.set_xlabel("Maturity", fontsize=12, color=TEXT_SECONDARY)
    ax.set_ylabel("Yield (%)", fontsize=12, color=TEXT_SECONDARY)

    # Build a title that lists all countries shown
    countries_shown = " vs ".join(all_yields_dict.keys())
    ax.set_title(
        f"Government Bond Yield Curves: {countries_shown} — {date}",
        fontsize=14,
        fontweight="bold",
        color=TEXT_PRIMARY,
        pad=14,
    )

    # Grid lines (horizontal only, solid hairline — cleaner and more
    # legible than a dashed rule)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)

    # Legend — no box, muted text, so the coloured lines still carry
    # the emphasis
    ax.legend(
        handles=legend_handles,
        fontsize=10,
        frameon=False,
        labelcolor=TEXT_SECONDARY,
    )

    plt.tight_layout()
    plt.show()
