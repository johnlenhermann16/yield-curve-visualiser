# app.py
#
# Streamlit + Plotly yield curve explorer. This is the interactive
# counterpart to main.py (which drives the static matplotlib chart) — the
# two chart implementations are kept fully separate; see charts/plot_curves.py
# vs charts/plot_curves_plotly.py.
#
# Data flow (relevant when this moves behind a React frontend later):
#   1. User picks a date and ticks which countries to show.
#   2. fetch_all_countries() calls each country's fetch function
#      (data/fetch_us.py, fetch_uk.py, fetch_germany.py) IN PARALLEL, one
#      thread per country, since each call is just waiting on a network
#      request. Every fetch function is individually cached with
#      @st.cache_data, so repeat requests for the same date are instant.
#   3. Each fetch function returns (actual_date, yields) — actual_date is
#      the nearest trading day that had data (may differ from the
#      requested date on a weekend/holiday), yields is a pd.Series of
#      yield % indexed by maturity label (e.g. "1Y", "10Y").
#   4. Failures (network errors, no data) are caught per-country here and
#      shown as a warning — one bad country never blocks the others or
#      crashes the app.

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from data.countries import COUNTRY_FETCHERS
from charts.plot_curves_plotly import build_yield_curve_figure
from charts.curve_utils import classify_curve, COUNTRY_COLOURS, DEFAULT_COLOUR, SINGLE_MATURITY_ONLY

# ---------------------------------------------------------------------------
# Educational layer — historical context, a dynamic curve explainer, and a
# quiz. Pure helper functions/data only; nothing here touches fetching or
# charting, and none of it is called until below the existing chart.
# ---------------------------------------------------------------------------


def get_historical_context(date_str):
    """
    Work out which broad economic period `date_str` (an ISO date string)
    falls into, and return a short first-year-finance-student explanation
    of what was going on with interest rates and bond markets at the time.

    Returns a dict: {"title": str, "explanation": str, "color": str}. `color`
    is one of "blue" (default), "orange" (2007–2009, 2020) or "red"
    (2022–2023) — used to pick the accent colour of the styled info box.
    """
    year = pd.Timestamp(date_str).year

    if year < 2007:
        return {
            "title": "Pre-2007: The \"Great Moderation\"",
            "explanation": (
                "Before 2007, the global economy had enjoyed roughly two decades of "
                "low inflation, steady growth and low volatility — economists nicknamed "
                "this the \"Great Moderation\". Central banks like the US Federal Reserve "
                "were gradually raising interest rates back to more normal levels after "
                "cutting them to deal with the early-2000s dot-com bust. Yield curves in "
                "this period tended to look fairly typical (upward-sloping), reflecting "
                "broad confidence that growth would continue."
            ),
            "color": "blue",
        }
    elif 2007 <= year <= 2009:
        return {
            "title": "2007–2009: The Global Financial Crisis",
            "explanation": (
                "This period covers the build-up to and aftermath of the Global "
                "Financial Crisis, triggered by the collapse of the US subprime "
                "mortgage market and the failure of major banks like Lehman Brothers. "
                "Central banks slashed interest rates to near zero in emergency moves "
                "to stop the financial system from seizing up, and the US Federal "
                "Reserve began \"quantitative easing\" (QE) — buying government bonds to "
                "push money into the economy and pull long-term yields down."
            ),
            "color": "orange",
        }
    elif 2010 <= year <= 2015:
        return {
            "title": "2010–2015: Post-Crisis Recovery",
            "explanation": (
                "In the years after the crisis, central banks kept interest rates near "
                "zero — a \"zero interest rate policy\", or ZIRP — to encourage borrowing "
                "and support a fragile recovery. At the same time, several eurozone "
                "countries struggled with unsustainable government debt, causing the "
                "European debt crisis and pushing their bond yields sharply higher. "
                "Yield curves in the US, UK and Germany stayed generally normal but very "
                "flat at the short end, since near-zero policy rates anchored short-term "
                "yields for years."
            ),
            "color": "blue",
        }
    elif 2016 <= year <= 2019:
        return {
            "title": "2016–2019: Gradual Normalisation",
            "explanation": (
                "As the recovery matured, the US Federal Reserve began slowly raising "
                "interest rates back towards more typical levels, a process known as "
                "\"policy normalisation\". Growth expectations stayed modest and inflation "
                "stayed low, so long-term yields didn't rise much even as short-term "
                "yields climbed — this flattened the US yield curve, which briefly "
                "inverted in parts during 2019 and was widely watched as an early "
                "warning sign of a possible slowdown."
            ),
            "color": "blue",
        }
    elif year == 2020:
        return {
            "title": "2020: The COVID-19 Shock",
            "explanation": (
                "When COVID-19 triggered a sudden, severe global shutdown in March "
                "2020, central banks cut interest rates to zero almost overnight and "
                "launched enormous QE programmes to keep credit markets functioning. "
                "Short-term yields collapsed to near zero, while massive government "
                "borrowing and eventual hopes of recovery kept longer-term yields "
                "comparatively higher, so yield curves steepened sharply — a normal "
                "shape, but for crisis-driven reasons rather than confident growth."
            ),
            "color": "orange",
        }
    elif year == 2021:
        return {
            "title": "2021: Recovery and Rising Inflation",
            "explanation": (
                "As economies reopened and stimulus spending flowed through the "
                "system, growth rebounded strongly — but so did inflation, partly due "
                "to supply-chain bottlenecks and surging demand. Markets began pricing "
                "in the likelihood that central banks would soon need to raise interest "
                "rates to bring inflation back under control, which started pushing "
                "short- and medium-term yields upward through the year."
            ),
            "color": "blue",
        }
    elif 2022 <= year <= 2023:
        return {
            "title": "2022–2023: The Fastest Rate Hike Cycle in 40 Years",
            "explanation": (
                "To fight the highest inflation since the early 1980s, central banks — "
                "especially the US Federal Reserve — raised interest rates at the "
                "fastest pace in decades. Short-term yields shot up faster than "
                "long-term yields, because markets expected the hikes to eventually "
                "cause a slowdown and future rate cuts, producing a deep inversion of "
                "the US yield curve and widespread recession fears. The Bank of Japan "
                "was the major outlier through all of this, keeping rates near zero "
                "and defending its yield curve control policy while every other major "
                "central bank hiked aggressively."
            ),
            "color": "red",
        }
    else:
        return {
            "title": "2024–2025: The Rate Cut Cycle Begins",
            "explanation": (
                "With inflation cooling from its 2022 peak, central banks started "
                "cutting interest rates again, moving cautiously to avoid reigniting "
                "price pressures or tipping the economy into recession. As cuts got "
                "underway, short-term yields began falling faster than long-term "
                "yields, and previously inverted curves started to \"re-normalise\" — "
                "moving back towards their typical upward-sloping shape. Meanwhile the "
                "Bank of Japan moved the opposite way, finally abandoning yield curve "
                "control and raising rates for the first time in decades."
            ),
            "color": "blue",
        }


# Accent colours for the historical context box, keyed by the "color" field
# get_historical_context() returns.
HISTORICAL_BOX_COLORS = {
    "blue": {"border": "#2a78d6", "background": "rgba(42, 120, 214, 0.08)"},
    "orange": {"border": "#eb6834", "background": "rgba(235, 104, 52, 0.08)"},
    "red": {"border": "#d64545", "background": "rgba(214, 69, 69, 0.08)"},
}


# Plain-English meaning, historical predictive track record, and one real
# example, keyed by the classification string classify_curve() returns.
CURVE_SHAPE_INFO = {
    "normal": {
        "meaning": (
            "A \"normal\" curve means longer-term bonds pay higher yields than "
            "short-term ones. That's the usual pattern, because investors want extra "
            "compensation — a \"term premium\" — for tying their money up for longer."
        ),
        "prediction": (
            "A normal curve doesn't predict trouble on its own — it's consistent with "
            "steady, ongoing growth, which is why it's the \"default\" shape most of "
            "the time."
        ),
        "example": (
            "Most of the mid-2010s (2013–2015) saw a normal curve alongside steady, "
            "if unspectacular, growth with no recession in sight."
        ),
    },
    "inverted": {
        "meaning": (
            "An \"inverted\" curve means short-term bonds pay HIGHER yields than "
            "long-term ones — the opposite of the usual pattern. That happens when "
            "investors expect interest rates (and growth) to fall in future, so "
            "they're happy to lock in today's yields for the long run."
        ),
        "prediction": (
            "Inverted curves have preceded almost every US recession since the 1950s, "
            "usually showing up 6 to 24 months before a downturn begins — it's one of "
            "the most closely-watched recession indicators in finance, though it "
            "doesn't pin down exactly when a recession will hit."
        ),
        "example": (
            "The clearest recent example is 2006–2007, when the US curve inverted "
            "about a year before the 2008 Global Financial Crisis; the same thing "
            "happened again in 2022–2023 ahead of persistent recession fears."
        ),
    },
    "flat": {
        "meaning": (
            "A \"flat\" curve means short- and long-term yields are very close "
            "together, so investors get barely any extra reward for lending "
            "longer-term. That usually signals uncertainty about what's next."
        ),
        "prediction": (
            "A flattening curve often shows up as growth expectations soften but "
            "haven't yet turned negative — it's frequently an early-warning stage on "
            "the way toward inversion, rather than a signal on its own."
        ),
        "example": (
            "The US curve flattened noticeably through 2018 and into 2019, shortly "
            "before it briefly inverted and just over a year before the COVID-19 "
            "recession hit in 2020."
        ),
    },
}

# Flag emoji per country, used to make tabs/expanders easier to scan.
COUNTRY_FLAGS = {
    "US": "🇺🇸",
    "UK": "🇬🇧",
    "Germany": "🇩🇪",
    "France": "🇫🇷",
    "Italy": "🇮🇹",
    "Spain": "🇪🇸",
    "Canada": "🇨🇦",
    "Switzerland": "🇨🇭",
    "Japan": "🇯🇵",
}


# "Did you know?" talking points — one per country, shown when that country
# is selected. Static, hand-written context on what makes each country's
# bond market distinctive; not derived from the fetched yields.
COUNTRY_FACTS = {
    "US": (
        "The US Treasury market is the world's largest and most liquid bond "
        "market. The Fed funds rate directly influences short-term yields, "
        "while long-term yields reflect inflation expectations and growth "
        "outlook. The 2022–2023 inversion was the deepest in 40 years."
    ),
    "UK": (
        "UK gilts are heavily influenced by both the Bank of England and "
        "fiscal policy. The September 2022 mini-budget crisis caused a "
        "historic gilt market crash, forcing the BOE to intervene as an "
        "emergency buyer — a rare event that showed how quickly sovereign "
        "bond markets can destabilise."
    ),
    "Germany": (
        "German Bunds are considered the eurozone's safe haven asset — the "
        "benchmark everything else is priced against. During EU crises, "
        "money floods into Bunds pushing yields down, while peripheral "
        "countries like Italy see yields spike — this spread is what "
        "markets watch during eurozone stress."
    ),
    "France": (
        "France's bond spread over Germany (OAT-Bund spread) is a key "
        "indicator of political and fiscal risk in the eurozone's second "
        "largest economy."
    ),
    "Italy": (
        "The Italy-Germany spread (BTP-Bund spread) is one of the most "
        "watched indicators in European finance — it spiked above 500bps "
        "during the 2011-2012 eurozone debt crisis when markets feared "
        "Italy might default or leave the euro."
    ),
    "Spain": (
        "Spain went from near-default in 2012 (yields above 7%) to a "
        "well-functioning bond market after Mario Draghi's \"whatever it "
        "takes\" speech — a textbook example of how central bank "
        "communication can move markets."
    ),
    "Canada": (
        "Canadian government bonds closely track US Treasuries due to deep "
        "trade and financial ties, but divergences between Bank of Canada "
        "and Fed policy create interesting spread dynamics worth watching."
    ),
    "Switzerland": (
        "Switzerland is the ultimate safe haven — during crises, demand for "
        "Swiss bonds is so intense that yields went deeply negative (below "
        "-1%) for years. Investors literally paid the Swiss government to "
        "hold their money safely."
    ),
    "Japan": (
        "The Bank of Japan held 10-year yields near 0% for years through "
        "yield curve control, buying unlimited bonds to defend the target. "
        "This made JGBs unique globally — artificially priced by policy "
        "rather than markets — and created enormous distortions when the "
        "BOJ finally abandoned YCC in 2024."
    ),
}

# Multiple-choice quiz bank. "inverted" and "normal" are conditional on what
# classify_curve() actually found in the fetched data; "spread" and "event"
# are always included.
QUIZ_QUESTIONS = {
    "inverted": {
        "question": "What does an inverted yield curve typically predict about the economy?",
        "options": [
            "Nothing — it's just a random market fluctuation with no historical pattern",
            "A likely economic slowdown or recession within the next 6–24 months",
            "That the central bank is about to cut interest rates to zero permanently",
            "That inflation will immediately return to target",
        ],
        "correct": "A likely economic slowdown or recession within the next 6–24 months",
        "explanation": (
            "Inverted curves have preceded almost every US recession since the 1950s, "
            "because they signal that investors expect rates and growth to fall in "
            "future. It's not a perfect predictor and the timing varies, but it's one "
            "of the most reliable recession indicators economists track."
        ),
    },
    "normal": {
        "question": "Why are long-term bond yields usually higher than short-term ones?",
        "options": [
            "Because long-term bonds are more heavily taxed",
            "Because investors demand extra compensation for tying up their money "
            "for longer and facing more uncertainty (a \"term premium\")",
            "Because governments always pay more interest on older debt",
            "Because short-term interest rates are fixed by law",
        ],
        "correct": (
            "Because investors demand extra compensation for tying up their money "
            "for longer and facing more uncertainty (a \"term premium\")"
        ),
        "explanation": (
            "This extra compensation is called the \"term premium\" — the longer you "
            "lend money, the more can go wrong (inflation, defaults, rate changes) "
            "before you get it back, so investors want to be paid more for that risk."
        ),
    },
    "spread": {
        "question": (
            "What does the \"2-10 spread\" (the difference between 2-year and "
            "10-year yields) commonly measure?"
        ),
        "options": [
            "The total government debt outstanding",
            "How steep or inverted the yield curve is, and by extension market "
            "expectations for future growth and rates",
            "The exchange rate between two currencies",
            "The default risk of a specific company",
        ],
        "correct": (
            "How steep or inverted the yield curve is, and by extension market "
            "expectations for future growth and rates"
        ),
        "explanation": (
            "The 2-10 spread is one of the most widely quoted shorthand measures of "
            "the yield curve's shape. A positive (wide) spread suggests a normal "
            "curve and growth expectations; a negative spread means inversion and "
            "often signals recession risk."
        ),
    },
    "event": {
        "question": "Which real-world event is widely associated with a major yield curve inversion?",
        "options": [
            "The 2006–2007 US yield curve inversion ahead of the 2008 Global Financial Crisis",
            "The launch of the euro currency in 1999",
            "The signing of the Bretton Woods Agreement in 1944",
            "The UK's decimalisation of currency in 1971",
        ],
        "correct": (
            "The 2006–2007 US yield curve inversion ahead of the 2008 Global "
            "Financial Crisis"
        ),
        "explanation": (
            "The US curve inverted in 2006–2007, about a year before Lehman Brothers "
            "collapsed and the Global Financial Crisis hit in 2008. The curve "
            "inverted again in 2022–2023 amid the fastest rate-hike cycle in 40 "
            "years, once more raising recession fears."
        ),
    },
}


st.set_page_config(page_title="Yield Curve Visualiser", layout="wide")

st.title("Government Bond Yield Curve Visualiser")
st.markdown(
    "<p style='color: grey; font-size: 1rem; margin-top: -0.75rem;'>"
    "Compare sovereign bond yields across maturities for major developed economies. "
    "Select a date and countries to explore how markets price growth, inflation "
    "and monetary policy risk.</p>",
    unsafe_allow_html=True,
)

selected_date = st.date_input("Date", value=date(2023, 1, 13))

# ---------------------------------------------------------------------------
# Comparison date pickers — up to 2 extra dates (3 total) on the same chart.
# Each slot gets a durable id (not a list position) so removing one slot's
# widget doesn't cause a later slot to inherit its stale session_state value.
# New slots start with no date picked (value=None shows an empty picker), so
# adding a slot never fetches anything on its own — a fetch only happens
# once the user actually picks a date for that slot.
# ---------------------------------------------------------------------------
MAX_COMPARISON_DATES = 2

st.session_state.setdefault("comparison_slots", [])
st.session_state.setdefault("next_comparison_slot_id", 0)

comparison_dates = []
for position, slot_id in enumerate(list(st.session_state.comparison_slots)):
    date_col, remove_col = st.columns([5, 1])
    with date_col:
        comparison_date = st.date_input(
            f"Comparison date {position + 1}",
            value=None,
            key=f"comparison_date_{slot_id}",
            help="Pick a date to overlay it on the chart.",
        )
    with remove_col:
        st.write("")  # vertical spacer so the button aligns with the date input
        if st.button("✕ Remove", key=f"remove_comparison_{slot_id}"):
            st.session_state.comparison_slots.remove(slot_id)
            st.rerun()
    comparison_dates.append(comparison_date)

if len(st.session_state.comparison_slots) < MAX_COMPARISON_DATES:
    add_label = "+ Add comparison date" if not st.session_state.comparison_slots else "+ Add another date"
    if st.button(add_label):
        st.session_state.comparison_slots.append(st.session_state.next_comparison_slot_id)
        st.session_state.next_comparison_slot_id += 1
        st.rerun()

# ---------------------------------------------------------------------------
# Country selector — a popover with a 3-column checkbox grid (colour dot +
# name, "10Y only" noted for the single-maturity countries) instead of a
# flat row of checkboxes, plus a live count and a badge row outside the
# popover so the current selection is visible without opening it.
# ---------------------------------------------------------------------------
country_names = list(COUNTRY_FETCHERS)

with st.popover("Select countries", width=680):
    popover_columns = st.columns(3)
    for i, country in enumerate(country_names):
        with popover_columns[i % 3]:
            # Each country is one row unit (checkbox + dot/name/note all on one
            # line), so the note text can't drift away from its own country's
            # checkbox the way it did when the dot/checkbox/note were split
            # into three separate nested columns with mismatched row heights.
            check_col, label_col = st.columns([1, 6])
            with check_col:
                st.checkbox(
                    country,
                    value=True,
                    key=f"country_checkbox_{country}",
                    label_visibility="collapsed",
                )
            with label_col:
                dot_colour = COUNTRY_COLOURS.get(country, DEFAULT_COLOUR)
                note_html = (
                    " <span style='color:grey; font-size:0.75rem;'>10Y only</span>"
                    if country in SINGLE_MATURITY_ONLY
                    else ""
                )
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:6px; "
                    f"margin-top:6px;'>"
                    f"<span style='width:10px; height:10px; border-radius:50%; "
                    f"background-color:{dot_colour}; display:inline-block; "
                    f"flex-shrink:0;'></span>"
                    f"<span>{country}</span>{note_html}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    selected_count = sum(
        1 for country in country_names if st.session_state.get(f"country_checkbox_{country}")
    )
    st.caption(f"{selected_count} of {len(country_names)} countries selected")

selected_countries = [
    country for country in country_names if st.session_state.get(f"country_checkbox_{country}")
]

if selected_countries:
    badges_html = '<div style="display:flex; flex-wrap:wrap; gap:6px; margin:0.5rem 0 1rem 0;">' + "".join(
        f'<span style="display:inline-flex; align-items:center; gap:6px; '
        f'background-color:rgba(120,120,120,0.14); border-radius:14px; '
        f'padding:4px 12px 4px 8px; font-size:0.85rem;">'
        f'<span style="width:9px; height:9px; border-radius:50%; '
        f'background-color:{COUNTRY_COLOURS.get(country, DEFAULT_COLOUR)}; '
        f'display:inline-block;"></span>{country}</span>'
        for country in selected_countries
    ) + "</div>"
    st.markdown(badges_html, unsafe_allow_html=True)

if any(country in SINGLE_MATURITY_ONLY for country in selected_countries):
    st.caption("Note: France, Italy and Spain use monthly data — not all dates will have values.")


def fetch_all_countries(countries, date_str):
    """
    Fetch yield data for multiple countries at once, in parallel.

    Each country's fetch is a slow network call but otherwise independent
    of the others, so running them on a thread pool (one thread per
    country) means the total wait is roughly the slowest single fetch,
    not the sum of all of them.

    Returns a dict keyed by country name:
        {
            "actual_date": str | None,  # trading day the data came from
            "yields": pd.Series,        # empty if the fetch failed
            "error": str | None,        # exception message, if any
        }
    A per-country exception (network failure, bad response, etc.) is
    caught here so it can't take down the other countries or the app.
    """
    results = {}

    # Worker threads don't automatically get Streamlit's ScriptRunContext,
    # and @st.cache_data needs one — without this, cached fetch calls made
    # from inside the thread pool fail. Grab the context on the main thread
    # and attach it to each worker before it calls a cached fetch function.
    # (This is Streamlit's documented pattern for combining caching with
    # threading, not something specific to this app.)
    script_ctx = get_script_run_ctx()

    def fetch_one(country):
        add_script_run_ctx(threading.current_thread(), script_ctx)
        return COUNTRY_FETCHERS[country](date_str)

    with ThreadPoolExecutor(max_workers=len(countries)) as executor:
        future_to_country = {
            executor.submit(fetch_one, country): country
            for country in countries
        }

        for future in as_completed(future_to_country):
            country = future_to_country[future]
            try:
                actual_date, yields = future.result()
                results[country] = {
                    "actual_date": actual_date,
                    "yields": yields,
                    "error": None,
                }
            except Exception as e:
                results[country] = {
                    "actual_date": None,
                    "yields": pd.Series(dtype=float),
                    "error": str(e),
                }

    return results


if not selected_countries:
    st.info("Select at least one country to see its yield curve.")
    st.stop()

date_str = selected_date.isoformat()
# Comparison dates in UI order, de-duplicated against the primary date and
# against each other (comparing the same date twice adds nothing). Slots
# where the user hasn't picked a date yet (comparison_date is None) are
# skipped silently — no fetch, no spinner, no warning for those.
comparison_date_strs = []
for comparison_date in comparison_dates:
    if comparison_date is None:
        continue
    comparison_date_str = comparison_date.isoformat()
    if comparison_date_str != date_str and comparison_date_str not in comparison_date_strs:
        comparison_date_strs.append(comparison_date_str)


def build_all_yields(fetch_results, countries, date_str, label=None):
    """
    Turn raw fetch results into the {country: yields} dict the chart and
    text analysis expect. Real failures (network errors, no data at all)
    still surface as an on-page warning — those are worth interrupting the
    user for. A weekend/holiday date falling back to the nearest trading
    day is NOT an error, just routine noise, so it's only printed to the
    console; the caller aggregates whether ANY adjustment happened across
    every country/date and shows a single one-line summary instead of one
    box per country.

    `label`, when given, is prefixed to warning messages so they stay
    unambiguous when several dates are being fetched at once. Left as None
    for the primary date so its messages are worded exactly as they always
    have been.

    Returns (all_yields, any_date_adjusted).
    """
    prefix = f"[{label}] " if label else ""
    all_yields = {}
    any_date_adjusted = False
    for country in countries:
        result = fetch_results[country]

        if result["error"] is not None:
            st.warning(f"{prefix}Couldn't fetch {country} data: {result['error']}")
            continue

        if result["yields"] is None or result["yields"].empty:
            if country not in SINGLE_MATURITY_ONLY:
                st.warning(f"{prefix}No {country} data available for {date_str}.")
            continue

        if result["actual_date"] and result["actual_date"] != date_str:
            print(
                f"{prefix}{country}: no data for {date_str} (likely a weekend or holiday) — "
                f"showing the nearest available trading day, {result['actual_date']}."
            )
            any_date_adjusted = True

        all_yields[country] = result["yields"]

    return all_yields, any_date_adjusted


with st.spinner("Fetching yield data..."):
    fetch_results = fetch_all_countries(selected_countries, date_str)
    comparison_fetch_results = [
        (comparison_date_str, fetch_all_countries(selected_countries, comparison_date_str))
        for comparison_date_str in comparison_date_strs
    ]

all_yields, any_date_adjusted = build_all_yields(fetch_results, selected_countries, date_str)

if not all_yields:
    st.stop()

# Each comparison date that actually returned data becomes a (date, yields)
# pair to overlay on the chart; ones that failed entirely are dropped with a
# warning instead of breaking the page.
comparison_pairs = []
for comparison_date_str, comparison_results in comparison_fetch_results:
    comparison_all_yields, comparison_adjusted = build_all_yields(
        comparison_results,
        selected_countries,
        comparison_date_str,
        label=f"Comparison date {comparison_date_str}",
    )
    any_date_adjusted = any_date_adjusted or comparison_adjusted
    if comparison_all_yields:
        comparison_pairs.append((comparison_date_str, comparison_all_yields))
    else:
        st.warning(f"No comparison data available for {comparison_date_str} — skipping it.")

dated_yields = [(date_str, all_yields)] + comparison_pairs

fig = build_yield_curve_figure(dated_yields)
st.plotly_chart(fig, use_container_width=True)

if any_date_adjusted:
    st.markdown(
        "<p style='color: grey; font-size: 0.85rem; margin-top: -0.5rem;'>"
        "Some dates adjusted to nearest trading day</p>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# 1. Historical context panel(s) — directly below the chart. Each date in
# `dated_yields` gets its own panel, side by side; `historical_context`
# always refers to the primary date, since that's what the curve explainer
# and quiz below use.
# ---------------------------------------------------------------------------
historical_context = get_historical_context(date_str)


def render_historical_context_box(context):
    colors = HISTORICAL_BOX_COLORS[context["color"]]
    st.markdown(
        f"""
        <div style="
            background-color: {colors['background']};
            border-left: 5px solid {colors['border']};
            border-radius: 6px;
            padding: 16px 20px;
            margin: 0 0 1.5rem 0;
            height: 100%;
        ">
            <div style="font-weight: 700; font-size: 1.05rem; margin-bottom: 6px;">
                {context['title']}
            </div>
            <div style="font-size: 0.95rem; line-height: 1.55;">
                {context['explanation']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


if comparison_pairs:
    context_columns = st.columns(len(dated_yields))
    with context_columns[0]:
        st.markdown(f"**Primary date — {date_str}**")
        render_historical_context_box(historical_context)
    for column, (comparison_date_str, _) in zip(context_columns[1:], comparison_pairs):
        with column:
            st.markdown(f"**Comparison date — {comparison_date_str}**")
            render_historical_context_box(get_historical_context(comparison_date_str))
else:
    render_historical_context_box(historical_context)

if comparison_pairs:
    st.markdown(
        "<p style='color: grey; font-size: 0.85rem;'>"
        "Analysis below reflects the primary date only (solid lines)</p>",
        unsafe_allow_html=True,
    )

st.subheader("What the data shows")
curve_analyses = {}
for country, yields in all_yields.items():
    if country in SINGLE_MATURITY_ONLY:
        # Only a single "10Y" point is available for these — not enough to
        # call a curve "shape", so they're reported honestly here and left
        # out of curve_analyses entirely (which keeps them out of the
        # curve explainer and quiz below, without needing to special-case
        # them again down there).
        ten_year = yields.get("10Y")
        if ten_year is not None:
            st.markdown(
                f"**{country}** — 10Y yield only: {ten_year:.2f}%. "
                f"Full curve not available from free APIs."
            )
        else:
            st.markdown(f"**{country}** — no data.")
        continue

    analysis = classify_curve(yields)
    print(f"[classify_curve] {country} ({date_str}): {analysis}")
    curve_analyses[country] = analysis
    if analysis is None:
        st.markdown(f"**{country}** — not enough maturities to classify the curve.")
        continue
    st.markdown(
        f"**{country}** — {analysis['classification'].capitalize()}. {analysis['explanation']}"
    )

# ---------------------------------------------------------------------------
# 2. Dynamic curve explainer — built from the actual fetched yields, not a
# static script, using classify_curve() for each country's shape. One tab
# per selected, classifiable country so the reader sees a single country's
# explanation at a time instead of every country's bullet points stacked
# down the page.
# ---------------------------------------------------------------------------
st.subheader("Why does the curve look like this?")

period_first_sentence = historical_context["explanation"].split(". ")[0] + "."

tab_countries = [country for country, analysis in curve_analyses.items() if analysis is not None]

if tab_countries:
    explainer_tabs = st.tabs(
        [f"{COUNTRY_FLAGS.get(country, '')} {country}".strip() for country in tab_countries]
    )
    for tab, country in zip(explainer_tabs, tab_countries):
        analysis = curve_analyses[country]
        shape = analysis["classification"]
        shape_info = CURVE_SHAPE_INFO[shape]
        accent = COUNTRY_COLOURS.get(country, DEFAULT_COLOUR)

        with tab:
            st.markdown(
                f"""
                <div style="
                    background-color: rgba(120, 120, 120, 0.08);
                    border-left: 5px solid {accent};
                    border-radius: 6px;
                    padding: 14px 18px;
                ">
                    <div style="font-weight: 700; font-size: 1rem; margin-bottom: 8px;">
                        {country} — {shape.capitalize()} curve
                    </div>
                    <div style="font-size: 0.9rem; line-height: 1.6;">
                        <b>What this shape means:</b> {shape_info['meaning']}<br><br>
                        <b>Why yields are here right now:</b> The {analysis['short_label']} yield is
                        {analysis['short_yield']:.2f}% and the {analysis['long_label']} yield is
                        {analysis['long_yield']:.2f}%. That fits the <i>{historical_context['title']}</i>
                        period — {period_first_sentence}<br><br>
                        <b>What this has historically predicted:</b> {shape_info['prediction']}<br><br>
                        <b>A real historical example:</b> {shape_info['example']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if country == "Japan":
                with st.expander("🇯🇵 Japan — Yield Curve Control explained"):
                    st.markdown(
                        "**Yield curve control (YCC):** The Bank of Japan capped "
                        "10-year JGB yields near 0% for years, buying unlimited "
                        "government bonds to defend that target and prevent "
                        "long-term rates from rising. It did this to keep "
                        "borrowing cheap and support growth after decades of "
                        "deflation. Because JGBs are one of the world's largest "
                        "bond markets, YCC's distortions — and its 2024 unwind — "
                        "ripple into global bond yields and capital flows."
                    )

# ---------------------------------------------------------------------------
# 2b. "Did you know?" — one static talking point per selected country on
# what makes its bond market distinctive, from COUNTRY_FACTS. Collapsed by
# default so the page shows a list of titles, not every fact expanded at once.
# ---------------------------------------------------------------------------
st.subheader("Did you know?")
for country in country_names:
    if country in selected_countries and country in COUNTRY_FACTS:
        flag = COUNTRY_FLAGS.get(country, "")
        with st.expander(f"{flag} {country} — Did you know?".strip()):
            st.markdown(COUNTRY_FACTS[country])

# ---------------------------------------------------------------------------
# 3. Interactive quiz — the first question adapts to what classify_curve()
# actually found in today's data; the last two are always shown.
# ---------------------------------------------------------------------------
detected_shapes = {a["classification"] for a in curve_analyses.values() if a is not None}

if "inverted" in detected_shapes:
    quiz_keys = ["inverted", "spread", "event"]
elif "normal" in detected_shapes:
    quiz_keys = ["normal", "spread", "event"]
else:
    quiz_keys = ["normal", "spread", "event"]

with st.expander("Test yourself", expanded=False):
    st.write("Answer each question, then press **Check answer** to see if you got it right.")
    for i, key in enumerate(quiz_keys, start=1):
        quiz = QUIZ_QUESTIONS[key]
        st.markdown(f"**Q{i}. {quiz['question']}**")
        choice = st.radio(
            "Select an answer:",
            quiz["options"],
            key=f"quiz_choice_{key}",
            index=None,
            label_visibility="collapsed",
        )
        if st.button("Check answer", key=f"quiz_check_{key}"):
            if choice is None:
                st.warning("Pick an answer first.")
            elif choice == quiz["correct"]:
                st.success(f"Correct! {quiz['explanation']}")
            else:
                st.error(f"Not quite. {quiz['explanation']}")
        st.divider()

# ---------------------------------------------------------------------------
# Footer — disclaimer and data source attribution, styled small/grey so it
# reads as background material rather than competing with the page content.
# ---------------------------------------------------------------------------
st.divider()
st.markdown(
    "<div style='color: grey; font-size: 0.8rem; line-height: 1.6;'>"
    "For educational purposes only. This tool is not financial advice and "
    "should not be used for investment decisions."
    "<br><br>"
    "<strong>Data sources:</strong>"
    "<ul style='margin-top: 0.25rem;'>"
    "<li>United States: Federal Reserve Economic Data (FRED), St. Louis Fed — fred.stlouisfed.org</li>"
    "<li>United Kingdom: Bank of England yield curve data — bankofengland.co.uk</li>"
    "<li>Germany: European Central Bank Statistical Data Warehouse — data-api.ecb.europa.eu</li>"
    "<li>France, Italy, Spain: ECB long-term interest rates (Maastricht criterion, 10Y benchmark)</li>"
    "<li>Canada: Bank of Canada Valet API — bankofcanada.ca</li>"
    "<li>Switzerland: Swiss National Bank data portal — data.snb.ch</li>"
    "<li>Japan: Ministry of Finance JGB yield data — mof.go.jp (OECD fallback for 10Y-only)</li>"
    "</ul>"
    "</div>",
    unsafe_allow_html=True,
)
