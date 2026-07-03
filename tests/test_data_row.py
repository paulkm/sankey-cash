import pandas as pd
import pytest

from sankey_cashflow.sankey_cash import DataRow


@pytest.fixture
def valid_row():
    return [
        pd.to_datetime('2023-01-01'),
        'Groceries',
        'Grocery Store',
        'food,essentials',
        'Monthly groceries',
        'Income',
        'Groceries',
        'computed',
        0,
        100.0,
        5.0,
        2.0,
        'Expense'
    ]


class TestValidate:

    def test_validate_valid_data(self, valid_row):
        assert DataRow.validate(valid_row, include_classifications=True) == valid_row

    def test_validate_invalid_amount_raises(self, valid_row):
        invalid_row = list(valid_row)
        invalid_row[9] = 'invalid_amount'
        with pytest.raises(Exception):
            DataRow.validate(invalid_row, include_classifications=True)

    def test_validate_non_nullable_field_raises(self, valid_row):
        invalid_row = list(valid_row)
        invalid_row[0] = None  # Date is required, non-nullable
        with pytest.raises(Exception):
            DataRow.validate(invalid_row, include_classifications=True)

    def test_validate_wrong_column_count_raises(self, valid_row):
        with pytest.raises(Exception):
            DataRow.validate(valid_row[:-1], include_classifications=True)

    def test_validate_disallowed_type_value_raises(self, valid_row):
        invalid_row = list(valid_row)
        invalid_row[7] = 'not_a_real_type'
        with pytest.raises(Exception):
            DataRow.validate(invalid_row, include_classifications=True)

    def test_validate_header_only_correct_order(self):
        header = ['Date', 'Category', 'Description', 'Tags', 'Comments', 'Source', 'Target',
                   'Type', 'Distribution', 'Amount', 'Sales Tax', 'Tips']
        result, error = DataRow.validate(header, header_only=True)
        assert result is True
        assert error is None

    def test_validate_header_only_wrong_order(self):
        header = ['Category', 'Date', 'Description', 'Tags', 'Comments', 'Source', 'Target',
                   'Type', 'Distribution', 'Amount', 'Sales Tax', 'Tips']
        result, error = DataRow.validate(header, header_only=True)
        assert result is False
        assert error is not None


class TestCreate:

    def test_create_matches_manually_built_row(self, valid_row):
        created = DataRow.create(
            date=pd.to_datetime('2023-01-01'),
            category_name='Groceries',
            source='Income',
            target='Groceries',
            amount=100.0,
            description='Grocery Store',
            sales_tax=5.0,
            tips=2.0,
            comment='Monthly groceries',
            tags='food,essentials',
            row_type='computed',
            distribution=0,
            classification='Expense'
        )
        assert created == valid_row

    def test_create_coerces_string_amount(self):
        created = DataRow.create(
            date=pd.to_datetime('2023-01-01'), category_name='Groceries',
            source='Income', target='Groceries', amount='100.0'
        )
        assert created[9] == 100.0

    def test_create_unparseable_amount_defaults_to_zero(self):
        created = DataRow.create(
            date=pd.to_datetime('2023-01-01'), category_name='Groceries',
            source='Income', target='Groceries', amount='not_a_number'
        )
        assert created[9] == 0

    def test_create_null_tips_defaults_to_zero(self):
        created = DataRow.create(
            date=pd.to_datetime('2023-01-01'), category_name='Groceries',
            source='Income', target='Groceries', amount=100.0, tips=None
        )
        assert created[11] == 0

    def test_create_null_distribution_defaults_to_zero(self):
        created = DataRow.create(
            date=pd.to_datetime('2023-01-01'), category_name='Groceries',
            source='Income', target='Groceries', amount=100.0, distribution=None
        )
        assert created[8] == 0

    def test_create_null_sales_tax_defaults_to_zero(self):
        created = DataRow.create(
            date=pd.to_datetime('2023-01-01'), category_name='Groceries',
            source='Income', target='Groceries', amount=100.0, sales_tax=None
        )
        assert created[10] == 0


class TestTagMatches:

    def test_returns_matching_tags(self):
        assert DataRow.tag_matches('food,essentials', ['food', 'luxury']) == ['food']

    def test_no_matches_returns_empty_list(self):
        assert DataRow.tag_matches('food,essentials', ['luxury']) == []

    def test_no_search_tags_returns_none(self):
        assert DataRow.tag_matches('food,essentials', None) is None

    def test_no_row_tags_returns_none(self):
        assert DataRow.tag_matches(None, ['food']) is None
