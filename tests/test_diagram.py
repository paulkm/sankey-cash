import pandas as pd
import plotly.graph_objects as go
import pytest

import sankey_cashflow.diagram as diagram_module
from sankey_cashflow import AppSettings, RowLabels, Transactions, build_sankey_figure, build_trend_figure, fetch_data


def _process(make_args, **overrides):
    args_kwargs = {'all_time': True, 'hover': 'Category'}
    args_kwargs.update(overrides)
    settings = AppSettings(make_args(**args_kwargs))
    src_target, df = fetch_data(settings)
    labels = RowLabels(src_target)
    txn = Transactions(df, labels, settings)
    txn.process()
    return txn, labels, settings


def _process_trend(make_args, **overrides):
    args_kwargs = {'all_time': True, 'dtype': 'trend'}
    args_kwargs.update(overrides)
    settings = AppSettings(make_args(**args_kwargs))
    src_target, df = fetch_data(settings)
    labels = RowLabels(src_target)
    txn = Transactions(df, labels, settings)
    txn.process_trend()
    return txn, labels, settings


@pytest.fixture
def processed_transactions(make_args):
    return _process(make_args)


@pytest.fixture
def trend_transactions(make_args):
    # Uses Transactions.process_trend() (the actual pipeline build_trend_figure is meant to run
    # against), rather than the fuller process() used by the Sankey tests/processed_transactions.
    return _process_trend(make_args)


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


class TestBuildTrendFigure:

    def test_returns_figure_with_traces(self, trend_transactions):
        txn, _, settings = trend_transactions
        settings.chart_resolution = 'week'
        fig = build_trend_figure(txn, settings)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_traces_have_real_data_not_all_nan(self, trend_transactions):
        # Regression test for the _sum_row_amount NaN-poisoning bug: a row with an empty Sales
        # Tax/Tips cell used to silently zero out its whole trace via float(nan) succeeding.
        txn, _, settings = trend_transactions
        fig = build_trend_figure(txn, settings)
        assert any(any(y == y for y in trace.y) for trace in fig.data)  # y == y is False for NaN

    def test_excludes_income_and_uncategorized(self, trend_transactions):
        txn, _, settings = trend_transactions
        settings.chart_resolution = 'month'
        fig = build_trend_figure(txn, settings)
        trace_names = [t.name for t in fig.data]
        assert not any(name.startswith('Income') for name in trace_names)
        assert not any(name.startswith('Uncategorized') for name in trace_names)

    def test_excludes_x_prefixed_classifications(self, trend_transactions):
        txn, _, settings = trend_transactions
        settings.chart_resolution = 'month'
        fig = build_trend_figure(txn, settings)
        trace_names = [t.name for t in fig.data]
        assert any(name.startswith('x') for name in txn.processed_data['Classification'].unique())
        assert not any(name.startswith('x') for name in trace_names)

    def test_does_not_mutate_processed_data(self, trend_transactions):
        txn, _, settings = trend_transactions
        settings.chart_resolution = 'month'
        original_columns = list(txn.processed_data.columns)
        build_trend_figure(txn, settings)
        assert list(txn.processed_data.columns) == original_columns

    def test_dollar_mode_yaxis_and_names(self, trend_transactions):
        txn, _, settings = trend_transactions
        settings.trend_mode = 'dollars'
        fig = build_trend_figure(txn, settings)
        assert fig.layout.yaxis.title.text == "Amount ($)"
        trace_names = [t.name for t in fig.data]
        # Dollar mode has exactly one trace per charted classification - no baseline/outlier
        # marker traces, since there's no baseline concept in this mode.
        assert not any('excluded from baseline' in name for name in trace_names)

    def test_percent_mode_is_default(self, trend_transactions):
        txn, _, settings = trend_transactions
        assert settings.trend_mode == 'percent'
        fig = build_trend_figure(txn, settings)
        assert fig.layout.yaxis.title.text == "% deviation from baseline"

    def test_quarter_resolution_has_fewer_points_than_week(self, trend_transactions):
        txn, _, settings = trend_transactions
        settings.chart_resolution = 'week'
        settings.trend_mode = 'dollars'
        week_points = len(build_trend_figure(txn, settings).data[0].x)
        settings.chart_resolution = 'quarter'
        quarter_points = len(build_trend_figure(txn, settings).data[0].x)
        assert quarter_points < week_points

    def test_year_resolution_collapses_single_year_sample_data_to_one_point(self, trend_transactions):
        # sample_data/expenses.csv only spans one calendar year, so a "year" bucket is degenerate
        # (one point, no line renders) - this documents that behavior rather than treating it as
        # a bug. Multi-year source data (see FEATURE_TRENDS.md stretch goal) would produce one
        # point per year instead, which does render as a real line.
        txn, _, settings = trend_transactions
        settings.chart_resolution = 'year'
        settings.trend_mode = 'dollars'
        fig = build_trend_figure(txn, settings)
        assert all(len(t.x) == 1 for t in fig.data)

    def test_explicit_multiple_resolution_accepted(self, trend_transactions):
        txn, _, settings = trend_transactions
        settings.chart_resolution = '3month'
        fig = build_trend_figure(txn, settings)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_trend_category_restricts_classifications(self, trend_transactions):
        txn, _, settings = trend_transactions
        available = [c for c in txn.processed_data['Classification'].unique()
                     if c not in ('Income', 'Uncategorized') and not c.startswith('x')]
        settings.trend_category = [available[0]]
        fig = build_trend_figure(txn, settings)
        trace_names = {t.name.split(' (')[0] for t in fig.data}
        assert trace_names == {available[0]}

    def test_trend_category_can_include_normally_hidden_classification(self, trend_transactions):
        txn, _, settings = trend_transactions
        hidden = next(c for c in txn.processed_data['Classification'].unique() if c.startswith('x'))
        settings.trend_category = [hidden]
        fig = build_trend_figure(txn, settings)
        trace_names = {t.name.split(' (')[0] for t in fig.data}
        assert hidden in trace_names

    def test_outlier_tag_excludes_row_from_trend(self, trend_transactions):
        txn, _, settings = trend_transactions
        classification = next(c for c in txn.processed_data['Classification'].unique()
                              if c not in ('Income', 'Uncategorized') and not c.startswith('x'))
        row_idx = txn.processed_data[txn.processed_data['Classification'] == classification].index[0]
        txn.processed_data.at[row_idx, 'Tags'] = 'Outlier'
        settings.trend_mode = 'dollars'
        settings.trend_category = [classification]
        fig_with_tag = build_trend_figure(txn, settings)
        txn.processed_data.at[row_idx, 'Tags'] = None
        fig_without_tag = build_trend_figure(txn, settings)
        assert fig_with_tag.data[0].y != fig_without_tag.data[0].y

    def test_low_baseline_falls_back_to_dollar_delta(self, trend_transactions, monkeypatch):
        # Force every classification below the low-baseline threshold to exercise the fallback
        # branch without having to hand-craft a near-zero-dollar dataset.
        txn, _, settings = trend_transactions
        monkeypatch.setattr(diagram_module, '_LOW_BASELINE_DOLLAR_THRESHOLD', float('inf'))
        fig = build_trend_figure(txn, settings)
        line_traces = [t for t in fig.data if 'excluded from baseline' not in t.name]
        assert len(line_traces) > 0
        assert all('baseline too low for %' in t.name for t in line_traces)

    def test_normal_baseline_percent_trace_has_dollar_delta_customdata(self, trend_transactions):
        txn, _, settings = trend_transactions
        fig = build_trend_figure(txn, settings)
        line_traces = [
            t for t in fig.data
            if 'excluded from baseline' not in t.name and 'baseline too low' not in t.name
        ]
        assert len(line_traces) > 0
        assert all(t.customdata is not None for t in line_traces)

    def test_outlier_tag_only_matches_exact_tag(self, trend_transactions):
        # DataRow.tag_matches() returns [] (falsy, but not None) when it checked and found no
        # overlap - a naive `is not None` check would wrongly treat every tagged row as excluded.
        txn, _, settings = trend_transactions
        tagged_rows = txn.processed_data[txn.processed_data['Tags'].notna()]
        assert len(tagged_rows) > 0
        assert not (tagged_rows['Tags'] == 'Outlier').all()
        filtered = diagram_module._exclude_outlier_tagged_rows(txn.processed_data, 'Outlier')
        assert len(filtered) == len(txn.processed_data)


class TestResampleFreqForResolution:

    @pytest.mark.parametrize('resolution,expected_freq', [
        ('day', 'D'), ('week', 'W'), ('month', 'ME'), ('quarter', '3ME'), ('year', 'YE'),
        ('3month', '3ME'), ('6week', '6W'), ('10day', '10D'),
    ])
    def test_recognized_resolutions(self, resolution, expected_freq):
        assert diagram_module._resample_freq_for_resolution(resolution) == expected_freq

    def test_unrecognized_resolution_falls_back_to_week(self):
        assert diagram_module._resample_freq_for_resolution('bogus') == 'W'


class TestBaselineAndOutliers:

    def test_mean_strategy(self):
        baseline, outliers = diagram_module._baseline_and_outliers([10, 20, 30], 'mean', 5)
        assert baseline == 20
        assert outliers == set()

    def test_median_strategy(self):
        baseline, outliers = diagram_module._baseline_and_outliers([10, 20, 100], 'median', 5)
        assert baseline == 20
        assert outliers == set()

    def test_trimmed_mean_excludes_high_and_low(self):
        # 10 points, trim 10% off each end -> excludes exactly one point per end (index 0 and 9
        # once sorted): the trimmed mean should ignore the low outlier (0) and high outlier (900).
        values = [0, 10, 10, 10, 10, 10, 10, 10, 10, 900]
        baseline, outliers = diagram_module._baseline_and_outliers(values, 'trimmed-mean', 10)
        assert baseline == 10
        assert outliers == {0, 9}

    def test_trimmed_mean_falls_back_to_mean_when_too_few_points(self):
        # trim_n would consume the whole series - falls back to a plain mean instead of erroring.
        baseline, outliers = diagram_module._baseline_and_outliers([5, 5], 'trimmed-mean', 50)
        assert baseline == 5
        assert outliers == set()

    def test_empty_values(self):
        baseline, outliers = diagram_module._baseline_and_outliers([], 'mean', 5)
        assert baseline == 0.0
        assert outliers == set()


class TestResolveClassifications:

    def test_hides_income_uncategorized_and_x_prefixed_by_default(self):
        df = pd.DataFrame({
            'Date': pd.to_datetime(['2023-01-01'] * 4),
            'Classification': ['Income', 'Uncategorized', 'xHidden', 'Auto'],
        })
        settings = type('S', (), {'trend_category': None})()
        assert diagram_module._resolve_classifications(df, settings) == ['Auto']

    def test_explicit_trend_category_overrides_hiding(self):
        df = pd.DataFrame({
            'Date': pd.to_datetime(['2023-01-01'] * 2),
            'Classification': ['Income', 'xHidden'],
        })
        settings = type('S', (), {'trend_category': ['Income', 'xHidden']})()
        assert diagram_module._resolve_classifications(df, settings) == ['Income', 'xHidden']

    def test_missing_trend_category_is_dropped_not_raised(self):
        df = pd.DataFrame({
            'Date': pd.to_datetime(['2023-01-01']),
            'Classification': ['Auto'],
        })
        settings = type('S', (), {'trend_category': ['Auto', 'DoesNotExist']})()
        assert diagram_module._resolve_classifications(df, settings) == ['Auto']
