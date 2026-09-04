import re
import statistics

import pandas as pd
import plotly.graph_objects as go

from .data_row import DataRow
from .utils import is_empty, logger

# pandas resample frequency alias for each single-unit --resolution preset.
_RESOLUTION_UNIT_FREQ = {"day": "D", "week": "W", "month": "ME"}
# pandas resample frequency alias for the named multi-unit --resolution presets.
_NAMED_RESOLUTION_FREQ = {"quarter": "3ME", "year": "YE"}
_RESOLUTION_MULTIPLIER_RE = re.compile(r"^(\d+)(day|week|month)$")

# Below this baseline ($), a percent-of-baseline comparison is too noisy to be meaningful (eg a
# category that's usually $0 with an occasional $12 purchase would show swings of hundreds of
# percent) - fall back to a plain $ delta from baseline for that classification instead.
_LOW_BASELINE_DOLLAR_THRESHOLD = 10.0


def _resample_freq_for_resolution(resolution):
    """
      Map a chart resolution - one of the named presets ("day", "week", "month", "quarter",
      "year"), or an explicit multiple like "3month" (see utils.normalize_chart_resolution for
      the parsing/validation side, which AppSettings runs --resolution values through before they
      ever reach here) - to the pandas resample frequency alias used to bucket transaction dates.
    """
    if resolution in _NAMED_RESOLUTION_FREQ:
        return _NAMED_RESOLUTION_FREQ[resolution]
    if resolution in _RESOLUTION_UNIT_FREQ:
        return _RESOLUTION_UNIT_FREQ[resolution]
    match = _RESOLUTION_MULTIPLIER_RE.match(resolution or "")
    if match:
        n, unit = match.groups()
        return f"{n}{_RESOLUTION_UNIT_FREQ[unit]}"
    logger.warning(f"Unrecognized chart resolution '{resolution}', defaulting to 'week'")
    return _RESOLUTION_UNIT_FREQ["week"]


def _hover_breakdown(transactions, node_name, hover_field):
    """
      Build hover text for a node: average spend/day plus a breakdown by hover_field, for all
      transactions flowing into that node. Returns "" if there's nothing to break down (eg. a
      node that's never a Target).
    """
    df = transactions.processed_data
    node_rows = df[df['Target'] == node_name]
    breakdown = node_rows.groupby([hover_field]).agg({'Amount': 'sum'})
    if len(breakdown) == 0:
        return ""
    days = (df['Date'].max() - df['Date'].min()).days
    avg_per_day = node_rows['Amount'].sum() / days if days else 0
    text = f"Avg/day: ${avg_per_day:.2f}<br>-------------------<br>Categories:<br>"
    for item, amount in breakdown['Amount'].items():
        text += f"{item}: ${amount:.2f}<br>"
    return text


def build_sankey_figure(transactions, labels, app_settings) -> go.Figure:
    """
      Build a plotly Sankey figure from processed transaction data. `transactions` must have
      already been through Transactions.process().
    """
    grouped = transactions.grouped_data.copy()  # Work on a copy - this function must be safe to call more than once.
    unique_nodes = list(pd.unique(grouped[['Source', 'Target']].values.ravel('K')))
    node_index = {name: idx for idx, name in enumerate(unique_nodes)}

    node_colors = [labels.get_attribute(name, "node_color") for name in unique_nodes]

    # Link color: prefer the target node's color, falling back to the source node's (or the
    # sheet's default color if neither is set).
    link_colors = []
    for source, target in zip(grouped['Source'], grouped['Target']):
        color = labels.get_attribute(target, "link_color", use_default=False)
        if not color:
            color = labels.get_attribute(source, "link_color")
        link_colors.append(color)

    node_settings = {
        'pad': 15,
        'thickness': 20,
        'line': dict(color='black', width=0.5),
        'label': unique_nodes,
        'color': node_colors,
    }

    if app_settings.hover:
        node_settings['customdata'] = [
            _hover_breakdown(transactions, name, app_settings.hover) for name in unique_nodes
        ]
        node_settings['hovertemplate'] = 'Total: %{value}<br>%{customdata}<extra></extra>'

    fig = go.Figure(data=[go.Sankey(
        valueformat="$.2f",
        node=node_settings,
        link=dict(
            source=grouped['Source'].map(node_index),
            target=grouped['Target'].map(node_index),
            value=grouped['Amount'],
            color=link_colors,
        )
    )])

    title = go.layout.Title({'font': {'family': 'Courier New', 'size': 12}, 'text': transactions.title})
    fig.update_layout(title=title)
    return fig


def _sum_row_amount(row):
    """
      Sum Amount + Sales Tax + Tips for a row, treating unparseable/missing values as zero.

      NOTE: empty Sales Tax/Tips cells come through as NaN, and float(nan) succeeds (it doesn't
      raise), so a plain try/except float() coercion silently poisons the whole sum to NaN for
      any row with an empty tax/tip value. Must check is_empty() first.
    """
    total = 0
    for col in ("Amount", "Sales Tax", "Tips"):
        if is_empty(row[col]):
            continue
        try:
            total += float(row[col])
        except (ValueError, TypeError):
            pass
    return total


def _exclude_outlier_tagged_rows(df, outlier_tag):
    """
      Drop any row tagged with `outlier_tag` (app_settings.trend_outlier_tag) entirely - both
      from the plotted series and from baseline computation. This is the explicit,
      user-controlled complement to the automatic statistical trimming done by
      _baseline_and_outliers() for trend_baseline='trimmed-mean': some outliers are real
      recurring costs the user wants excluded on purpose, not statistical noise.
    """
    if not outlier_tag:
        return df
    # DataRow.tag_matches() returns None if it couldn't check at all (empty search/row tags), but
    # an empty list (falsy, not None) when it checked and found no overlap - must use a truthy
    # check here, not `is not None`, or every tagged row gets treated as a match.
    mask = df["Tags"].apply(lambda tags: bool(DataRow.tag_matches(tags, [outlier_tag])))
    return df[~mask]


def _resolve_classifications(df, app_settings):
    """
      Determine which Classifications to chart, in order.

      If app_settings.trend_category is set, chart exactly those (in the order given), ignoring
      the 'Income'/'Uncategorized'/'x'-prefix hiding convention below - an explicit request
      should always be honored. Otherwise chart everything except 'Income', 'Uncategorized', and
      anything prefixed with 'x' (a convention used in sample_data/labels.csv, eg.
      'xEntertainment', to hide a classification from trend charts by default).
    """
    all_classifications = sorted(df["Classification"].dropna().unique())
    if app_settings.trend_category:
        missing = [c for c in app_settings.trend_category if c not in all_classifications]
        if missing:
            logger.warning(f"trend_category value(s) not found in data: {missing}")
        return [c for c in app_settings.trend_category if c in all_classifications]
    return [c for c in all_classifications if c not in ("Income", "Uncategorized") and not c.startswith('x')]


def _resample_series(df, classification, date_idx, freq, fill_value):
    series = df.loc[df["Classification"] == classification].groupby("Date")["Total Amount"].sum()
    series.index = pd.DatetimeIndex(series.index)
    series = series.reindex(date_idx, fill_value=fill_value)
    return series.resample(freq, label="left").sum()


def _resample_gapped_series(df, classification, date_idx, freq):
    """
      Resample a classification's daily totals to `freq`, treating any period with zero total
      activity as a gap (NaN) rather than a literal $0 - used by both trend_mode branches so "no
      activity this period" is drawn identically either way: skipped and connected across
      (connectgaps=True), not shown as a dip to $0 / -100%.
    """
    series = _resample_series(df, classification, date_idx, freq, fill_value=float("nan"))
    return series.replace(0, float("nan"))


def _baseline_and_outliers(values, strategy, trim_percent):
    """
      Compute a baseline value for a series of period totals, plus the positions (indices into
      `values`) of any points excluded from that computation by trimming.

      NOTE: this only supports fixed-baseline strategies (mean/median/trimmed-mean), each
      comparing every period to one reference value computed across the whole charted range. A
      "prior-period" strategy - comparing each point to the one immediately before it instead
      (pandas' Series.pct_change() would do this directly) - was discussed but deferred; see
      FEATURE_TRENDS.md open question 5. Add it here as another branch if/when it's picked up.
    """
    n = len(values)
    if n == 0:
        return 0.0, set()
    if strategy == "median":
        return statistics.median(values), set()
    if strategy == "trimmed-mean":
        trim_n = int(n * trim_percent / 100)
        if trim_n <= 0 or n - 2 * trim_n < 1:
            return statistics.mean(values), set()
        order = sorted(range(n), key=lambda i: values[i])
        outlier_positions = set(order[:trim_n]) | set(order[-trim_n:])
        included = [values[i] for i in range(n) if i not in outlier_positions]
        return statistics.mean(included), outlier_positions
    return statistics.mean(values), set()  # "mean", or an unrecognized value


def build_trend_figure(transactions, app_settings) -> go.Figure:
    """
      Build a plotly line chart of spend over time, grouped by Classification.

      Two modes, via app_settings.trend_mode:
      - 'dollars': raw $ totals per period, one trace per classification sharing a single Y-axis.
        Reasonable for a single classification (or a few with similar baselines - see
        trend_category), but multiple wildly-different-baseline classifications will flatten the
        smaller ones. Sparse periods are shown as gaps (connectgaps), not zeros.
      - 'percent' (default): each classification is plotted as % deviation from its own baseline
        (see app_settings.trend_baseline), so classifications with very different $ baselines
        stay comparable on one Y-axis. Like 'dollars', a period with no activity is a gap
        (connectgaps), not a dip to -100% - it's excluded from both the plotted line and the
        baseline calculation, so an occasional truly-empty period doesn't distort either. Points
        trimmed out of the baseline calculation (trend_baseline='trimmed-mean') are still drawn,
        just marked as excluded, rather than silently vanishing. Classifications whose baseline is
        too close to $0 for a percent comparison to be meaningful fall back to a $ delta from
        baseline instead (see _LOW_BASELINE_DOLLAR_THRESHOLD).

      Rows tagged with app_settings.trend_outlier_tag are dropped entirely before charting (see
      _exclude_outlier_tagged_rows). 'Income', 'Uncategorized', and any classification prefixed
      with 'x' are hidden by default unless app_settings.trend_category explicitly requests them
      (see _resolve_classifications).
    """
    df = transactions.processed_data.assign(**{"Total Amount": None})
    df["Total Amount"] = df.apply(_sum_row_amount, axis=1)
    df = _exclude_outlier_tagged_rows(df, app_settings.trend_outlier_tag)

    classifications = _resolve_classifications(df, app_settings)
    if not classifications:
        logger.warning("No classifications available to chart for the trend diagram.")

    date_idx = pd.date_range(start=df["Date"].min(), end=df["Date"].max())
    freq = _resample_freq_for_resolution(app_settings.chart_resolution)

    fig = go.Figure()

    if app_settings.trend_mode == "dollars":
        for classification in classifications:
            series = _resample_gapped_series(df, classification, date_idx, freq)
            fig.add_trace(go.Scatter(
                x=series.index.to_list(), y=series.to_list(), mode='lines', name=classification, connectgaps=True
            ))
        fig.update_layout(yaxis_title="Amount ($)")
        return fig

    # percent mode (default)
    for classification in classifications:
        series = _resample_gapped_series(df, classification, date_idx, freq)
        values = series.to_list()
        # Baseline/outlier computation only ever sees real (non-gap) periods - an empty period
        # shouldn't pull the baseline toward zero any more than it should show as a -100% dip.
        valid_positions = [i for i, v in enumerate(values) if v == v]  # v == v is False for NaN
        non_gap_values = [values[i] for i in valid_positions]
        if not non_gap_values:
            continue  # nothing to compare against for this classification
        baseline, trimmed_positions = _baseline_and_outliers(
            non_gap_values, app_settings.trend_baseline, app_settings.trend_trim
        )
        outlier_positions = {valid_positions[p] for p in trimmed_positions}

        if abs(baseline) < _LOW_BASELINE_DOLLAR_THRESHOLD:
            deltas = [v - baseline if v == v else float("nan") for v in values]
            fig.add_trace(go.Scatter(
                x=series.index.to_list(), y=deltas, mode='lines', connectgaps=True,
                name=f"{classification} ($ delta, baseline too low for %)",
                hovertemplate="$%{y:+.2f} vs baseline<extra></extra>",
            ))
            continue

        pct_values = [(v - baseline) / baseline * 100 if v == v else float("nan") for v in values]
        dollar_deltas = [v - baseline if v == v else float("nan") for v in values]
        fig.add_trace(go.Scatter(
            x=series.index.to_list(), y=pct_values, mode='lines', connectgaps=True,
            name=classification, customdata=dollar_deltas,
            hovertemplate="%{y:+.1f}%<br>≈ $%{customdata:+.2f} vs baseline<extra></extra>",
        ))

        if outlier_positions:
            ordered = sorted(outlier_positions)
            fig.add_trace(go.Scatter(
                x=[series.index[i] for i in ordered], y=[pct_values[i] for i in ordered],
                mode='markers', marker=dict(symbol='x', size=9), legendgroup=classification,
                name=f"{classification} (excluded from baseline)",
                hovertemplate="Excluded from baseline calc<br>%{y:+.1f}%<extra></extra>",
            ))
    fig.update_layout(yaxis_title="% deviation from baseline")
    return fig
