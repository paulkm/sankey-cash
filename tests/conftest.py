import pytest

from sankey_cashflow.sankey_cash import AppSettings, RowLabels, Transactions
import pandas as pd


class Args:
    """
    Stand-in for the argparse.Namespace that AppSettings expects. Every field defaults to the
    value used by a plain `python -m sankey_cashflow ...` invocation against the sample data;
    override individual kwargs in a test to exercise a specific branch.
    """
    def __init__(self, **overrides):
        defaults = dict(
            source='sample_data/expenses.csv',
            audit=False,
            sheet=None,
            srcmap='sample_data/labels.csv',
            range=None,
            separate_tax=False,
            verbose=False,
            creds=None,
            distributions=False,
            all_time=False,
            recurring=False,
            hover=None,
            dtype=None,
            tags=None,
            tag_override=False,
            feed_in=False,
            exclude=None,
            stores=None,
        )
        defaults.update(overrides)
        for key, value in defaults.items():
            setattr(self, key, value)


@pytest.fixture
def make_args():
    return Args


@pytest.fixture
def default_app_settings(make_args):
    return AppSettings(make_args())


@pytest.fixture
def sample_labels_data():
    return [
        {
            'Category Name': 'House',
            'Type': 'computed',
            'Source': 'Income',
            'Target': 'House',
            'Classification': 'Expense',
            'Link color': 'rgba(153, 187, 255, 0.8)',
            'Node color': 'rgba(102, 153, 255, 1)',
            'Comments': ''
        },
        {
            'Category Name': 'Groceries',
            'Type': 'computed',
            'Source': 'Income',
            'Target': 'Groceries',
            'Classification': 'Expense',
            'Link color': 'rgba(153, 187, 255, 0.8)',
            'Node color': 'rgba(102, 153, 255, 1)',
            'Comments': ''
        }
    ]


@pytest.fixture
def sample_row_labels(sample_labels_data):
    return RowLabels(sample_labels_data)


@pytest.fixture
def sample_transactions_df():
    data = {
        'Date': ['2023-01-01', '2023-01-02'],
        'Category': ['Groceries', 'House'],
        'Description': ['Grocery Store', 'Mortgage'],
        'Tags': [None, 'Recurring'],
        'Comments': ['', ''],
        'Source': [None, None],
        'Target': [None, None],
        'Type': ['computed', 'computed'],
        'Distribution': [None, None],
        'Amount': [100.0, 200.0],
        'Sales Tax': [5.0, 10.0],
        'Tips': [2.0, 3.0],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_transactions(sample_transactions_df, sample_row_labels, default_app_settings):
    return Transactions(sample_transactions_df, sample_row_labels, default_app_settings)


TRANSACTION_COLUMNS = [
    'Date', 'Category', 'Description', 'Tags', 'Comments', 'Source', 'Target',
    'Type', 'Distribution', 'Amount', 'Sales Tax', 'Tips'
]


@pytest.fixture
def make_transactions_df():
    """
    Build a transactions DataFrame from partial row dicts, filling in defaults for any
    column not specified. Column order/set must exactly match DataRow.fields for
    Transactions._validate_df() to accept it.
    """
    def _make(rows):
        defaults = {
            'Description': '', 'Tags': None, 'Comments': '', 'Source': None, 'Target': None,
            'Type': '', 'Distribution': None, 'Sales Tax': None, 'Tips': None,
        }
        full_rows = []
        for row in rows:
            full_row = dict(defaults)
            full_row.update(row)
            full_rows.append({col: full_row[col] for col in TRANSACTION_COLUMNS})
        return pd.DataFrame(full_rows)
    return _make
