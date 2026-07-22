# charts/plot_curves_plotly.py
#
# Plotly rendering only — this is the interactive counterpart to
# plot_curves.py (matplotlib). The two never import from each other; shared,
# non-plotting logic (maturity sorting, inversion detection, colours) lives
# in curve_utils.py.

import plotly.graph_objects as go

from charts.curve_utils import (
    COUNTRY_COLOURS,
    DEFAULT_COLOUR,
    SINGLE_MATURITY_ONLY,
    find_inversion_zones,
    get_all_maturities,
    maturity_to_years,
)

# Chart chrome — matches the light surface / muted ink styling of the
# matplotlib chart so both renderers read as one system.
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
AXIS_TEXT = "#1a1a1a"


# Line/marker style per date position: index 0 is always the primary date
# (solid, filled markers); later dates cycle through this list. The app
# currently caps the UI at 3 dates total (1 primary + 2 comparison), so only
# the first three entries are ever used, but the cycle degrades gracefully
# if that cap ever changes.
DATE_LINE_STYLES = [None, "dash", "dot", "dashdot"]
DATE_MARKER_SYMBOLS = ["circle", "circle-open", "square-open", "diamond-open"]


def build_yield_curve_figure(dated_yields):
    """
    Build an interactive Plotly figure for one or more countries' yield
    curves, optionally overlaying the same countries on additional dates
    for comparison. Hovering a point shows its yield; no values are drawn
    statically on the chart.

    Parameters:
    -----------
    dated_yields : list of (date, {country: pd.Series}) tuples
        The first tuple is the primary date: solid lines, filled markers,
        and inversion-zone shading. Every subsequent tuple is a comparison
        date, drawn in the same colour as each country's primary curve but
        with a distinct dash pattern (dashed, then dotted, ...) and no
        inversion shading, to keep the chart readable. A single-tuple list
        renders identically to a plain single-date chart.

    Returns:
    --------
    plotly.graph_objects.Figure
    """
    if not dated_yields:
        raise ValueError("dated_yields must contain at least one (date, yields) pair")

    multi_date = len(dated_yields) > 1

    # Combined maturities axis across every date/country combination.
    maturity_source = {}
    for date_idx, (_, yields_dict) in enumerate(dated_yields):
        for country, yields in yields_dict.items():
            maturity_source[f"{date_idx}_{country}"] = yields
    all_maturities = get_all_maturities(maturity_source)
    maturity_positions = {m: i for i, m in enumerate(all_maturities)}

    fig = go.Figure()
    any_inversions = False

    for date_idx, (date_str, yields_dict) in enumerate(dated_yields):
        is_primary = date_idx == 0
        dash_style = DATE_LINE_STYLES[date_idx % len(DATE_LINE_STYLES)]
        marker_symbol = DATE_MARKER_SYMBOLS[date_idx % len(DATE_MARKER_SYMBOLS)]

        for country, yields in yields_dict.items():
            if yields.empty:
                continue

            colour = COUNTRY_COLOURS.get(country, DEFAULT_COLOUR)
            sorted_maturities = sorted(yields.index, key=maturity_to_years)
            x_positions = [maturity_positions[m] for m in sorted_maturities]
            y_yields = [float(yields[m]) for m in sorted_maturities]
            trace_name = f"{country} ({date_str})" if multi_date else country
            single_maturity = country in SINGLE_MATURITY_ONLY

            if single_maturity:
                # Only one real data point (10Y) — a "line" would be
                # misleading, so this renders as a lone diamond marker with
                # a tooltip that says plainly why there's no full curve.
                fig.add_trace(go.Scatter(
                    x=x_positions,
                    y=y_yields,
                    mode="markers",
                    name=trace_name,
                    marker=dict(
                        size=13 if is_primary else 10,
                        symbol="diamond" if is_primary else "diamond-open",
                        color=colour,
                        line=dict(color=SURFACE if is_primary else colour, width=1.5),
                    ),
                    hovertemplate=(
                        "<b>%{y:.2f}%</b> — " + trace_name
                        + " 10Y yield only — full curve not available from free APIs<extra></extra>"
                    ),
                ))
                continue

            line_style = dict(color=colour, width=2)
            if dash_style:
                line_style["dash"] = dash_style

            if is_primary:
                marker_style = dict(
                    size=9,
                    color=colour,
                    line=dict(color=SURFACE, width=1.5),  # surface ring, same as matplotlib version
                )
            else:
                marker_style = dict(
                    size=7,
                    color=colour,
                    symbol=marker_symbol,
                    line=dict(color=colour, width=1.5),
                )

            fig.add_trace(go.Scatter(
                x=x_positions,
                y=y_yields,
                mode="lines+markers",
                name=trace_name,
                text=sorted_maturities,
                line=line_style,
                marker=marker_style,
                # Values lead, the series name follows — matches tooltip hierarchy guidance.
                hovertemplate="<b>%{y:.2f}%</b> — " + trace_name + " %{text}<extra></extra>",
            ))

            # Comparison-date curves are excluded on purpose — inversion
            # shading for several overlapping curves would be unreadable.
            if is_primary:
                inversion_zones = find_inversion_zones(x_positions, y_yields)
                if inversion_zones:
                    any_inversions = True
                    for x_start, x_end in inversion_zones:
                        fig.add_vrect(
                            x0=x_start, x1=x_end,
                            fillcolor=colour, opacity=0.12,
                            line_width=0, layer="below",
                        )

    if any_inversions:
        # Legend-only dummy trace explaining the inversion shading.
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, color="grey", opacity=0.4, symbol="square"),
            name="Inversion zone (short > long)",
            hoverinfo="skip",
        ))

    countries_shown = " vs ".join(dated_yields[0][1].keys())
    dates_shown = " | ".join(date_str for date_str, _ in dated_yields)
    title_text = f"Government Bond Yield Curves: {countries_shown} — {dates_shown}"

    fig.update_layout(
        title=dict(
            text=title_text,
            font=dict(size=18, color=TEXT_PRIMARY, family="Arial, sans-serif"),
        ),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Arial, sans-serif"),
        hovermode="x unified",
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=TEXT_SECONDARY),
        ),
        margin=dict(l=60, r=30, t=70, b=50),
        xaxis=dict(
            title=dict(text="Maturity", font=dict(color=AXIS_TEXT)),
            tickmode="array",
            tickvals=list(range(len(all_maturities))),
            ticktext=all_maturities,
            tickfont=dict(color=AXIS_TEXT),
            color=AXIS_TEXT,
            linecolor=BASELINE,
            gridcolor=GRIDLINE,
            showgrid=False,
        ),
        yaxis=dict(
            title=dict(text="Yield (%)", font=dict(color=AXIS_TEXT)),
            tickfont=dict(color=AXIS_TEXT),
            color=AXIS_TEXT,
            gridcolor=GRIDLINE,
            linecolor=BASELINE,
            zeroline=False,
        ),
    )

    return fig
