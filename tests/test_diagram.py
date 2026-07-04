import plotly.graph_objects as go
import pytest

from sankey_cashflow import AppSettings, RowLabels, Transactions, build_line_figure, build_sankey_figure, fetch_data


def _process(make_args, **overrides):
    args_kwargs = {'all_time': True, 'hover': 'Category'}
    args_kwargs.update(overrides)
    settings = AppSettings(make_args(**args_kwargs))
    src_target, df = fetch_data(settings)
    labels = RowLabels(src_target)
    txn = Transactions(df, labels, settings)
    txn.process()
    return txn, labels, settings


@pytest.fixture
def processed_transactions(make_args):
    return _process(make_args)


class TestBuildSankeyFigure:

    def test_returns_figure(self, processed_transactions):
        txn, labels, settings = processed_transactions
        fig = build_sankey_figure(txn, labels, settings)
        assert isinstance(fig, go.Figure)

    def test_links_match_grouped_data_length(self, processed_transactions):
        txn, labels, settings = processed_transactions
        fig = build_sankey_figure(txn, labels, settings)
        assert len(fig.data[0].link.value) == len(txn.grouped_data)

    def test_title_uses_transactions_title(self, processed_transactions):
        txn, labels, settings = processed_transactions
        fig = build_sankey_figure(txn, labels, settings)
        assert fig.layout.title.text == txn.title

    def test_safe_to_call_more_than_once(self, processed_transactions):
        # Regression test: the original script mutated grouped_data in place (remapped Source/Target
        # to integer indices), so a second call would silently produce a broken figure.
        txn, labels, settings = processed_transactions
        fig1 = build_sankey_figure(txn, labels, settings)
        fig2 = build_sankey_figure(txn, labels, settings)
        assert list(fig1.data[0].link.value) == list(fig2.data[0].link.value)
        assert list(fig1.data[0].node.label) == list(fig2.data[0].node.label)

    def test_hover_customdata_present_when_enabled(self, processed_transactions):
        txn, labels, settings = processed_transactions
        fig = build_sankey_figure(txn, labels, settings)
        assert fig.data[0].node.customdata is not None

    def test_no_hover_customdata_when_disabled(self, make_args):
        # AppSettings only disables hover for the string 'none' (or 'no'/'false') - omitting the
        # flag entirely defaults to hover='Category' (enabled).
        txn, labels, settings = _process(make_args, hover='none')
        assert settings.hover is None
        fig = build_sankey_figure(txn, labels, settings)
        assert fig.data[0].node.customdata is None


class TestBuildLineFigure:

    def test_returns_figure_with_traces(self, processed_transactions):
        txn, _, settings = processed_transactions
        settings.chart_resolution = 'week'
        fig = build_line_figure(txn, settings)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_excludes_income_and_uncategorized(self, processed_transactions):
        txn, _, settings = processed_transactions
        settings.chart_resolution = 'month'
        fig = build_line_figure(txn, settings)
        trace_names = [t.name for t in fig.data]
        assert 'Income' not in trace_names
        assert 'Uncategorized' not in trace_names

    def test_excludes_x_prefixed_classifications(self, processed_transactions):
        txn, _, settings = processed_transactions
        settings.chart_resolution = 'month'
        fig = build_line_figure(txn, settings)
        trace_names = [t.name for t in fig.data]
        assert any(name.startswith('x') for name in txn.processed_data['Classification'].unique())
        assert not any(name.startswith('x') for name in trace_names)

    def test_does_not_mutate_processed_data(self, processed_transactions):
        txn, _, settings = processed_transactions
        settings.chart_resolution = 'month'
        original_columns = list(txn.processed_data.columns)
        build_line_figure(txn, settings)
        assert list(txn.processed_data.columns) == original_columns
