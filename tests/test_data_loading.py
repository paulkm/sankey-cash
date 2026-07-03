import pandas as pd
import pytest

from sankey_cashflow.sankey_cash import read_csv_as_df, fetch_data, DataRow


class TestReadCsvAsDf:

    def test_reads_single_csv(self):
        df = read_csv_as_df('sample_data/expenses.csv')
        assert len(df) == 33
        assert list(df.columns) == [
            'Date', 'Category', 'Description', 'Tags', 'Comments', 'Source', 'Target',
            'Type', 'Distribution', 'Amount', 'Sales Tax', 'Tips'
        ]

    def test_concatenates_multiple_csvs(self, tmp_path):
        cols = 'Date,Category,Description,Tags,Comments,Source,Target,Type,Distribution,Amount,Sales Tax,Tips\n'
        row = '1/1/23,Groceries,Store,,,,,,,10.00,,\n'
        file_a = tmp_path / 'a.csv'
        file_b = tmp_path / 'b.csv'
        file_a.write_text(cols + row)
        file_b.write_text(cols + row + row)
        df = read_csv_as_df([str(file_a), str(file_b)])
        assert len(df) == 3

    def test_missing_file_raises(self):
        with pytest.raises(Exception):
            read_csv_as_df('does_not_exist.csv')

    def test_non_csv_file_raises(self, tmp_path):
        bad_file = tmp_path / 'data.txt'
        bad_file.write_text('not a csv')
        with pytest.raises(Exception):
            read_csv_as_df(str(bad_file))


class TestFetchData:

    def test_loads_sample_labels_and_transactions(self, default_app_settings):
        src_target, df = fetch_data(default_app_settings)
        assert isinstance(src_target, list)
        assert len(src_target) > 0
        assert 'Category Name' in src_target[0]
        assert len(df) == 33

    def test_amount_column_normalized_to_float(self, default_app_settings):
        _, df = fetch_data(default_app_settings)
        assert all(isinstance(v, float) for v in df['Amount'])
        # First data row in sample_data/expenses.csv is "$4,000.00"
        assert df.iloc[0]['Amount'] == 4000.0

    def test_header_matches_data_row_schema(self, default_app_settings):
        _, df = fetch_data(default_app_settings)
        is_valid = DataRow.validate(df.columns.to_list(), True)
        assert is_valid[0] is True
