import pandas as pd
import plotly.graph_objects as go


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
    """
    total = 0
    for col in ("Amount", "Sales Tax", "Tips"):
        try:
            total += float(row[col])
        except (ValueError, TypeError):
            pass
    return total


def build_line_figure(transactions, app_settings) -> go.Figure:
    """
      Build a plotly line chart of spend over time, grouped by Classification.

      NOTE: less mature than build_sankey_figure() - can get noisy for large datasets, doesn't
      fill in zero-value gaps for categories with sparse activity, and doesn't support a log
      scale. 'Income', 'Uncategorized', and any classification prefixed with 'x' (a convention
      used in sample_data/labels.csv, eg. 'xEntertainment') are hidden by default.
    """
    df = transactions.processed_data.assign(**{"Total Amount": None})
    df["Total Amount"] = df.apply(_sum_row_amount, axis=1)

    classifications = sorted(df["Classification"].unique())
    date_idx = pd.date_range(start=df["Date"].min(), end=df["Date"].max())

    fig = go.Figure()
    for classification in classifications:
        if classification in ("Income", "Uncategorized"):
            continue
        if classification.startswith('x'):
            continue
        series = df[df["Classification"] == classification].groupby('Date')["Total Amount"].sum()
        series.index = pd.DatetimeIndex(series.index)
        series = series.reindex(date_idx, fill_value=float("nan"))  # connectgaps needs NaN, not 0
        if app_settings.chart_resolution == 'day':
            series = series.resample('D', label='left').sum()
        elif app_settings.chart_resolution == 'week':
            series = series.resample('W', label='left').sum()
        elif app_settings.chart_resolution == 'month':
            series = series.resample('ME', label='left').sum()
        series = series.replace(0, float("nan"))
        fig.add_trace(go.Scatter(
            y=series.to_list(), x=series.index.to_list(), mode='lines', name=classification, connectgaps=True
        ))
    return fig
