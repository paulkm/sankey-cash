import pandas as pd
import pytest

from sankey_cashflow import AppSettings


class TestDefaultInitialization:

    def test_default_initialization(self, default_app_settings):
        settings = default_app_settings
        assert settings.data_source == 'sample_data/expenses.csv'
        assert settings.audit_mode is False
        assert settings.data_sheet == 'Transactions_*'
        assert settings._labels_source == 'sample_data/labels.csv'
        assert settings.filter_dates is None
        assert settings.separate_taxes is False
        assert settings.verbose is False
        assert settings._g_creds == './google_service_account_key.json'
        assert settings.distribute_amounts is False
        assert settings.all_time is False
        assert settings.recurring is False
        assert settings.base_title == 'Cashflow'
        assert settings._date_filter_start is None
        assert settings._date_filter_end is None
        assert settings.tags is None
        assert settings.feed_in is None
        assert settings.exclude_tags is None
        assert settings.stores is None
        assert settings.tag_override is False
        assert settings.hover == 'Category'
        assert settings.chart_resolution == 'week'
        assert settings.sales_tax_classification == 'Taxes'
        assert settings.tip_classification == 'xTips'
        assert settings.diagram_type == 'sankey'
        assert settings.trend_mode == 'percent'
        assert settings.trend_baseline == 'trimmed-mean'
        assert settings.trend_trim == 5.0
        assert settings.trend_category is None
        assert settings.trend_outlier_tag == 'Outlier'
        assert settings.scatter_smoothing == 'lowess'
        assert settings.scatter_lowess_frac == 0.3
        assert settings.scatter_ma_window == 'month'
        assert settings.colors == {}

    def test_verbose_logging(self, make_args):
        settings = AppSettings(make_args(verbose=True))
        assert settings.verbose is True


class TestHoverOption:

    @pytest.mark.parametrize('hover_arg', ['desc', 'stores', 'description', 'DESC'])
    def test_hover_maps_to_description(self, make_args, hover_arg):
        settings = AppSettings(make_args(hover=hover_arg))
        assert settings.hover == 'Description'

    @pytest.mark.parametrize('hover_arg', ['none', 'no', 'false', 'NONE'])
    def test_hover_disabled(self, make_args, hover_arg):
        settings = AppSettings(make_args(hover=hover_arg))
        assert settings.hover is None

    def test_hover_unrecognized_keeps_default(self, make_args):
        settings = AppSettings(make_args(hover='unknown-option'))
        assert settings.hover == 'Category'


class TestDiagramType:

    @pytest.mark.parametrize('dtype_arg,expected', [
        ('sankey', 'sankey'), ('trend', 'trend'), ('TREND', 'trend'), ('bar', 'bar'),
    ])
    def test_recognized_dtype(self, make_args, dtype_arg, expected):
        settings = AppSettings(make_args(dtype=dtype_arg))
        assert settings.diagram_type == expected

    def test_unrecognized_dtype_keeps_default(self, make_args):
        settings = AppSettings(make_args(dtype='pie'))
        assert settings.diagram_type == 'sankey'

    def test_scatter_dtype_with_single_category(self, make_args):
        settings = AppSettings(make_args(dtype='scatter', trend_category='Auto'))
        assert settings.diagram_type == 'scatter'


class TestChartResolution:

    @pytest.mark.parametrize('resolution_arg,expected', [
        ('day', 'day'), ('week', 'week'), ('MONTH', 'month'), ('quarter', 'quarter'), ('YEAR', 'year'),
        ('3 months', '3month'), ('3months', '3month'), ('1 month', 'month'), ('6 weeks', '6week'),
    ])
    def test_recognized_resolution(self, make_args, resolution_arg, expected):
        settings = AppSettings(make_args(resolution=resolution_arg))
        assert settings.chart_resolution == expected

    @pytest.mark.parametrize('resolution_arg', ['fortnight', '0 months', '-1 week', '   '])
    def test_unrecognized_resolution_keeps_default(self, make_args, resolution_arg):
        settings = AppSettings(make_args(resolution=resolution_arg))
        assert settings.chart_resolution == 'week'


class TestTrendOptions:

    @pytest.mark.parametrize('mode_arg,expected', [
        ('dollars', 'dollars'), ('percent', 'percent'), ('PERCENT', 'percent')
    ])
    def test_recognized_trend_mode(self, make_args, mode_arg, expected):
        settings = AppSettings(make_args(trend_mode=mode_arg))
        assert settings.trend_mode == expected

    def test_unrecognized_trend_mode_keeps_default(self, make_args):
        settings = AppSettings(make_args(trend_mode='logarithmic'))
        assert settings.trend_mode == 'percent'

    @pytest.mark.parametrize('baseline_arg,expected', [
        ('mean', 'mean'), ('median', 'median'), ('trimmed-mean', 'trimmed-mean'), ('MEAN', 'mean')
    ])
    def test_recognized_trend_baseline(self, make_args, baseline_arg, expected):
        settings = AppSettings(make_args(trend_baseline=baseline_arg))
        assert settings.trend_baseline == expected

    def test_unrecognized_trend_baseline_keeps_default(self, make_args):
        settings = AppSettings(make_args(trend_baseline='mode'))
        assert settings.trend_baseline == 'trimmed-mean'

    def test_trend_trim_parses_float(self, make_args):
        settings = AppSettings(make_args(trend_trim='10'))
        assert settings.trend_trim == 10.0

    @pytest.mark.parametrize('bad_trim', ['not-a-number', '-1', '50', '100'])
    def test_trend_trim_out_of_range_keeps_default(self, make_args, bad_trim):
        settings = AppSettings(make_args(trend_trim=bad_trim))
        assert settings.trend_trim == 5.0

    def test_trend_category_split_and_stripped(self, make_args):
        settings = AppSettings(make_args(trend_category=' Auto , Housing Exp '))
        assert settings.trend_category == ['Auto', 'Housing Exp']

    def test_trend_outlier_tag_override(self, make_args):
        settings = AppSettings(make_args(trend_outlier_tag='Skip'))
        assert settings.trend_outlier_tag == 'Skip'


class TestScatterOptions:

    @pytest.mark.parametrize('smoothing_arg,expected', [
        ('lowess', 'lowess'), ('moving-average', 'moving-average'), ('LOWESS', 'lowess')
    ])
    def test_recognized_scatter_smoothing(self, make_args, smoothing_arg, expected):
        settings = AppSettings(make_args(dtype='scatter', trend_category='Auto', scatter_smoothing=smoothing_arg))
        assert settings.scatter_smoothing == expected

    def test_unrecognized_scatter_smoothing_keeps_default(self, make_args):
        settings = AppSettings(make_args(dtype='scatter', trend_category='Auto', scatter_smoothing='spline'))
        assert settings.scatter_smoothing == 'lowess'

    def test_scatter_lowess_frac_parses_float(self, make_args):
        settings = AppSettings(make_args(dtype='scatter', trend_category='Auto', scatter_lowess_frac='0.5'))
        assert settings.scatter_lowess_frac == 0.5

    @pytest.mark.parametrize('bad_frac', ['not-a-number', '0', '-0.1', '1.5'])
    def test_scatter_lowess_frac_out_of_range_keeps_default(self, make_args, bad_frac):
        settings = AppSettings(make_args(dtype='scatter', trend_category='Auto', scatter_lowess_frac=bad_frac))
        assert settings.scatter_lowess_frac == 0.3

    def test_scatter_ma_window_normalized(self, make_args):
        settings = AppSettings(make_args(dtype='scatter', trend_category='Auto', scatter_ma_window='3 weeks'))
        assert settings.scatter_ma_window == '3week'

    def test_scatter_ma_window_unrecognized_keeps_default(self, make_args):
        settings = AppSettings(make_args(dtype='scatter', trend_category='Auto', scatter_ma_window='fortnight'))
        assert settings.scatter_ma_window == 'month'

    def test_scatter_requires_trend_category(self, make_args):
        with pytest.raises(Exception):
            AppSettings(make_args(dtype='scatter'))

    def test_scatter_rejects_multiple_trend_categories(self, make_args):
        with pytest.raises(Exception):
            AppSettings(make_args(dtype='scatter', trend_category='Auto, Housing Exp'))


class TestBarOptions:

    def test_bar_dtype_does_not_require_trend_category(self, make_args):
        # Unlike scatter, bar charts multiple classifications - no single-category requirement.
        settings = AppSettings(make_args(dtype='bar'))
        assert settings.diagram_type == 'bar'

    def test_bar_dtype_with_trend_mode_does_not_raise(self, make_args):
        # --trend-mode is ignored (with a warning) by --dtype bar, rather than erroring.
        settings = AppSettings(make_args(dtype='bar', trend_mode='percent'))
        assert settings.diagram_type == 'bar'


class TestTagsStoresExclude:

    def test_tags_split_and_stripped(self, make_args):
        settings = AppSettings(make_args(tags=' Ford , Dodge '))
        assert settings.tags == ['Ford', 'Dodge']

    def test_tag_override_requires_tags(self, make_args):
        settings = AppSettings(make_args(tags='Ford', tag_override=True))
        assert settings.tag_override is True

    def test_tag_override_ignored_without_tags(self, make_args):
        settings = AppSettings(make_args(tags=None, tag_override=True))
        assert settings.tag_override is False

    def test_feed_in_requires_tags(self, make_args):
        settings = AppSettings(make_args(tags='Ford', feed_in=True))
        assert settings.feed_in is True

    def test_feed_in_ignored_without_tags(self, make_args):
        settings = AppSettings(make_args(tags=None, feed_in=True))
        assert settings.feed_in is None

    def test_exclude_split_and_stripped(self, make_args):
        settings = AppSettings(make_args(exclude=' Onetime , Refund '))
        assert settings.exclude_tags == ['Onetime', 'Refund']

    def test_stores_split_and_stripped(self, make_args):
        settings = AppSettings(make_args(stores=' Costco , Amazon '))
        assert settings.stores == ['Costco', 'Amazon']

    def test_tags_and_stores_together_raises(self, make_args):
        with pytest.raises(Exception):
            AppSettings(make_args(tags='Ford', stores='Costco'))


class TestDateFilterSetters:

    def test_date_filter_start_setter(self, default_app_settings):
        default_app_settings.date_filter_start = '2023-01-01'
        assert default_app_settings.date_filter_start == pd.to_datetime('2023-01-01')

    def test_date_filter_start_setter_empty_is_none(self, default_app_settings):
        default_app_settings.date_filter_start = ''
        assert default_app_settings.date_filter_start is None

    def test_date_filter_end_setter(self, default_app_settings):
        default_app_settings.date_filter_end = '2023-12-31'
        assert default_app_settings.date_filter_end == pd.to_datetime('2023-12-31')

    def test_date_filter_end_setter_empty_is_none(self, default_app_settings):
        default_app_settings.date_filter_end = ''
        assert default_app_settings.date_filter_end is None


class TestCredsAndLabelsSetters:

    def test_g_creds_setter_missing_file_raises(self, default_app_settings):
        with pytest.raises(Exception):
            default_app_settings.g_creds = 'invalid_path.json'

    def test_labels_source_setter_missing_file_raises(self, default_app_settings):
        with pytest.raises(Exception):
            default_app_settings.labels_source = 'invalid_path.csv'

    def test_labels_source_setter_valid_csv(self, default_app_settings):
        default_app_settings.labels_source = 'sample_data/labels.csv'
        assert default_app_settings.labels_source == 'sample_data/labels.csv'


class TestSourceValidation:

    def test_source_data_location_csv(self, default_app_settings):
        assert default_app_settings.source_data_location() == 'sample_data/expenses.csv'

    def test_source_data_location_gsheet(self, make_args):
        settings = AppSettings(make_args(
            source='My Workbook', sheet='Transactions_2023', creds='sample_data/labels.csv'
        ))
        assert settings.source_data_location() == 'My Workbook: Transactions_2023'

    def test_validate_sources_missing_source_raises(self, default_app_settings):
        default_app_settings.data_source = None
        with pytest.raises(Exception):
            default_app_settings.validate_sources()

    def test_validate_sources_csv_requires_csv_labels(self, make_args):
        with pytest.raises(Exception):
            AppSettings(make_args(source='sample_data/expenses.csv', srcmap='Sources-Targets'))

    def test_validate_sources_missing_csv_file_raises(self, make_args):
        with pytest.raises(Exception):
            AppSettings(make_args(source='does_not_exist.csv'))

    def test_validate_sources_gsheet_requires_sheet_name(self, make_args):
        with pytest.raises(Exception):
            AppSettings(make_args(source='My Workbook', sheet=None, srcmap='Sources-Targets'))

    def test_validate_sources_gsheet_requires_creds_file(self, make_args):
        with pytest.raises(Exception):
            AppSettings(make_args(
                source='My Workbook', sheet='Transactions_2023',
                srcmap='Sources-Targets', creds='missing_creds.json'
            ))
