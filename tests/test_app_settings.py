import pandas as pd
import pytest

from sankey_cashflow.sankey_cash import AppSettings


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
        assert settings.chart_resolution is None
        assert settings.sales_tax_classification == 'Taxes'
        assert settings.tip_classification == 'xTips'
        assert settings.diagram_type == 'sankey'
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

    @pytest.mark.parametrize('dtype_arg,expected', [('sankey', 'sankey'), ('line', 'line'), ('LINE', 'line')])
    def test_recognized_dtype(self, make_args, dtype_arg, expected):
        settings = AppSettings(make_args(dtype=dtype_arg))
        assert settings.diagram_type == expected

    def test_unrecognized_dtype_keeps_default(self, make_args):
        settings = AppSettings(make_args(dtype='pie'))
        assert settings.diagram_type == 'sankey'


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
