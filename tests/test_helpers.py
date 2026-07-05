import pandas as pd
import pytest

from sankey_cashflow import (
    is_null,
    is_empty,
    validate_date_string,
    normalize_amounts,
    df_date_filter,
)


class TestIsNull:

    @pytest.mark.parametrize('value', [None, float('nan'), pd.NaT, 'None', 'NaN', 'null'])
    def test_null_values(self, value):
        assert is_null(value) is True

    @pytest.mark.parametrize('value', ['', 0, 'valid_string', 123, pd.Timestamp('2023-01-01')])
    def test_non_null_values(self, value):
        assert is_null(value) is False


class TestIsEmpty:

    @pytest.mark.parametrize('value', [None, float('nan'), pd.NaT, 'None', 'NaN', 'null', ''])
    def test_empty_values(self, value):
        assert is_empty(value) is True

    @pytest.mark.parametrize('value', [0, 'valid_string', 123, pd.Timestamp('2023-01-01'), [], {}, (), set()])
    def test_non_empty_values(self, value):
        assert is_empty(value) is False

    def test_zero_is_empty_when_nonzero_flag_set(self):
        assert is_empty(0, nonzero=True) is True
        assert is_empty(0.0, nonzero=True) is True

    def test_nonzero_number_not_empty_with_flag(self):
        assert is_empty(1, nonzero=True) is False
        assert is_empty(0.25, nonzero=True) is False

    def test_nonzero_flag_does_not_affect_non_numeric(self):
        assert is_empty('valid_string', nonzero=True) is False


class TestValidateDateString:

    @pytest.mark.parametrize('value', ['2023-01-01', '1901-12-31', '2099-01-01'])
    def test_valid_yyyy_mm_dd(self, value):
        assert validate_date_string(value) is True

    @pytest.mark.parametrize('value', ['01/01/2023', '12/31/1901', '01/01/2099'])
    def test_valid_mm_dd_yyyy(self, value):
        assert validate_date_string(value) is True

    @pytest.mark.parametrize('value', ['1899-12-31', '2100-01-01', '12/31/1899', '01/01/2100'])
    def test_out_of_range_year(self, value):
        assert validate_date_string(value) is False

    @pytest.mark.parametrize('value', ['2023-00-01', '2023-13-01', '00/01/2023', '13/01/2023'])
    def test_invalid_month(self, value):
        assert validate_date_string(value) is False

    @pytest.mark.parametrize('value', ['2023-01-00', '2023-01-32', '01/00/2023', '01/32/2023'])
    def test_invalid_day(self, value):
        assert validate_date_string(value) is False

    @pytest.mark.parametrize('value', ['2023/01/01', '01-01-2023', '2023.01.01', '01.01.2023', 'invalid_date'])
    def test_unrecognized_format(self, value):
        assert validate_date_string(value) is False

    def test_allow_empty_true(self):
        assert validate_date_string('', allow_empty=True) is True
        assert validate_date_string(None, allow_empty=True) is True

    def test_allow_empty_false_raises_on_empty_string(self):
        with pytest.raises(Exception):
            validate_date_string('', allow_empty=False)

    def test_allow_empty_false_raises_on_none(self):
        with pytest.raises(Exception):
            validate_date_string(None, allow_empty=False)


class TestNormalizeAmounts:

    def test_dollar_and_comma_stripped(self):
        row = pd.Series({'Amount': '$4,000.00', 'Sales Tax': '', 'Tips': ''})
        result = normalize_amounts(row)
        assert result['Amount'] == 4000.0

    def test_plain_float_string_converted(self):
        row = pd.Series({'Amount': '40.00', 'Sales Tax': '1.50', 'Tips': ''})
        result = normalize_amounts(row)
        assert result['Amount'] == 40.0
        assert result['Sales Tax'] == 1.5

    def test_already_numeric_left_alone(self):
        row = pd.Series({'Amount': 40.0, 'Sales Tax': 1.5, 'Tips': 0.0})
        result = normalize_amounts(row)
        assert result['Amount'] == 40.0

    def test_empty_values_untouched(self):
        row = pd.Series({'Amount': '40.00', 'Sales Tax': '', 'Tips': None})
        result = normalize_amounts(row)
        assert result['Sales Tax'] == ''
        assert result['Tips'] is None


class TestDfDateFilter:

    @pytest.fixture
    def dates_df(self):
        return pd.DataFrame({
            'Date': pd.to_datetime(['2023-01-01', '2023-02-01', '2023-03-01']),
            'Amount': [10.0, 20.0, 30.0],
        })

    def test_filters_inclusive_range(self, dates_df):
        result = df_date_filter(dates_df, pd.to_datetime('2023-01-15'), pd.to_datetime('2023-02-15'))
        assert len(result) == 1
        assert result.iloc[0]['Amount'] == 20.0

    def test_no_bounds_returns_unchanged(self, dates_df):
        result = df_date_filter(dates_df, None, None)
        assert len(result) == 3

    def test_only_start_bound(self, dates_df):
        result = df_date_filter(dates_df, pd.to_datetime('2023-02-01'), None)
        assert len(result) == 2

    def test_only_end_bound(self, dates_df):
        result = df_date_filter(dates_df, None, pd.to_datetime('2023-02-01'))
        assert len(result) == 2

    def test_empty_result_raises(self, dates_df):
        with pytest.raises(Exception):
            df_date_filter(dates_df, pd.to_datetime('2024-01-01'), pd.to_datetime('2024-02-01'))
