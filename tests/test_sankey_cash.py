import unittest
from src.sankey_cashflow.sankey_cash import (
    AppSettings,
    RowLabels,
    Transactions,
    DataRow,
    is_null,
    is_empty,
    validate_date_string

)
from pathlib import Path
import pandas as pd
import logging
import networkx as nx

logger = logging.getLogger()

def test_utils():
    from src.sankey_cashflow.sankey_cash import SankeyUtils
    assert SankeyUtils is not None

class TestAppSettings(unittest.TestCase):
    class Args:
        def __init__(
                self,
                source,
                audit,
                sheet,
                srcmap,
                range,
                separate_tax,
                verbose,
                creds,
                distributions,
                all_time,
                recurring,
                hover,
                dtype,
                tags,
                tag_override,
                feed_in,
                exclude,
                stores):
            self.source = source
            self.audit = audit
            self.sheet = sheet
            self.srcmap = srcmap
            self.range = range
            self.separate_tax = separate_tax
            self.verbose = verbose
            self.creds = creds
            self.distributions = distributions
            self.all_time = all_time
            self.recurring = recurring
            self.hover = hover
            self.dtype = dtype
            self.tags = tags
            self.tag_override = tag_override
            self.feed_in = feed_in
            self.exclude = exclude
            self.stores = stores

    def setUp(self):
        self.args = self.Args(
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
            stores=None
        )

    def test_default_initialization(self):
        settings = AppSettings(self.args)
        self.assertEqual(settings.data_source, 'sample_data/expenses.csv')
        self.assertFalse(settings.audit_mode)
        self.assertEqual(settings.data_sheet, 'Transactions_*')
        self.assertEqual(settings._labels_source, 'sample_data/labels.csv')
        self.assertIsNone(settings.filter_dates)
        self.assertFalse(settings.separate_taxes)
        self.assertFalse(settings.verbose)
        self.assertEqual(settings._g_creds, './google_service_account_key.json')
        self.assertFalse(settings.distribute_amounts)
        self.assertFalse(settings.all_time)
        self.assertFalse(settings.recurring)
        self.assertEqual(settings.base_title, 'Cashflow')
        self.assertIsNone(settings._date_filter_start)
        self.assertIsNone(settings._date_filter_end)
        self.assertIsNone(settings.tags)
        self.assertIsNone(settings.feed_in)
        self.assertIsNone(settings.exclude_tags)
        self.assertIsNone(settings.stores)
        self.assertFalse(settings.tag_override)
        self.assertEqual(settings.hover, 'Category')
        self.assertIsNone(settings.chart_resolution)
        self.assertEqual(settings.sales_tax_classification, 'Taxes')
        self.assertEqual(settings.tip_classification, 'xTips')
        self.assertEqual(settings.diagram_type, 'sankey')
        self.assertEqual(settings.colors, {})

    def test_verbose_logging(self):
        self.args.verbose = True
        settings = AppSettings(self.args)
        self.assertEqual(settings.verbose, True)
        # TODO: review logging tests
        # self.assertEqual(logger.level, logging.DEBUG)
        # self.assertEqual(logger.handlers[0].level, logging.DEBUG)

    def test_date_filter_start_setter(self):
        settings = AppSettings(self.args)
        settings.date_filter_start = '2023-01-01'
        self.assertEqual(settings.date_filter_start, pd.to_datetime('2023-01-01'))

    def test_date_filter_end_setter(self):
        settings = AppSettings(self.args)
        settings.date_filter_end = '2023-12-31'
        self.assertEqual(settings.date_filter_end, pd.to_datetime('2023-12-31'))

    def test_g_creds_setter(self):
        settings = AppSettings(self.args)
        with self.assertRaises(Exception):
            settings.g_creds = 'invalid_path.json'

    def test_labels_source_setter(self):
        settings = AppSettings(self.args)
        with self.assertRaises(Exception):
            settings.labels_source = 'invalid_path.csv'

    def test_source_data_location(self):
        settings = AppSettings(self.args)
        self.assertEqual(settings.source_data_location(), 'sample_data/expenses.csv')

    def test_validate_sources(self):
        settings = AppSettings(self.args)
        settings.data_source = None
        with self.assertRaises(Exception):
            settings.validate_sources()


class TestRowLabels(unittest.TestCase):

    def setUp(self):
        self.label_data = [
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
        self.row_labels = RowLabels(self.label_data)

    def test_init(self):
        self.assertEqual(len(self.row_labels.data), 2)
        self.assertIn('House', self.row_labels._lookup)
        self.assertIn('Groceries', self.row_labels._lookup)
        self.assertIsInstance(self.row_labels._digraph, nx.DiGraph)

    def test_get_longest_path(self):
        longest_path = self.row_labels.get_longest_path()
        self.assertIsInstance(longest_path, list)
        self.assertGreaterEqual(len(longest_path), 1)

    def test_get_path(self):
        path = self.row_labels.get_path('Income', 'House')
        # import pdb; pdb.set_trace()
        self.assertIsInstance(path, list)
        self.assertGreaterEqual(len(path), 1)

    def test_get_label(self):
        label = self.row_labels.get_label('House')
        self.assertIsNotNone(label)
        self.assertEqual(label['source'], 'Income')
        self.assertEqual(label['target'], 'House')

    def test_get_attribute(self):
        source = self.row_labels.get_attribute('House', 'source')
        self.assertEqual(source, 'Income')
        target = self.row_labels.get_attribute('House', 'target')
        self.assertEqual(target, 'House')
        classification = self.row_labels.get_attribute('House', 'classification')
        self.assertEqual(classification, 'Expense')

    def test_print_graph(self):
        self.row_labels.print_graph('test_graph.png')
        self.assertTrue(Path('test_graph.png').is_file())

class TestTransactions(unittest.TestCase):

    def setUp(self):
        self.data = {
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
        self.df = pd.DataFrame(self.data)
        self.labels_data = [
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
        self.labels_obj = RowLabels(self.labels_data)
        self.app_settings = AppSettings(TestAppSettings.Args(
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
            stores=None
        ))
        self.transactions = Transactions(self.df, self.labels_obj, self.app_settings)

    def test_init(self):
        self.assertEqual(self.transactions.length, 2)
        self.assertEqual(self.transactions.earliest_date, pd.to_datetime('2023-01-01'))
        self.assertEqual(self.transactions.latest_date, pd.to_datetime('2023-01-02'))

    def test_validate_df(self):
        self.assertTrue(self.transactions._validate_df())

    def test_audit(self):
        audit_data = pd.DataFrame({
            'Date': [pd.to_datetime('2023-01-01')],
            'Amount': [107],
            'Description': ['Grocery Store']
        })
        report = self.transactions.audit(audit_data)
        # import pdb; pdb.set_trace()
        self.assertEqual(report, "")

    def test_process(self):
        self.transactions.process()
        # These attr appear in the class but do not appear to be set anywhere
        # self.assertTrue(self.transactions.tips_processed)
        # self.assertTrue(self.transactions.sales_tax_processed)
        self.assertTrue(self.transactions.surplus_deficit_processed)

    def test_process_line(self):
        # Skipping for now.
        # self.transactions.process_line()
        # These attr appear in the class but do not appear to be set anywhere
        # self.assertTrue(self.transactions.tips_processed)
        # self.assertTrue(self.transactions.sales_tax_processed)
        # self.assertTrue(self.transactions.surplus_deficit_processed)
        pass

    def test_filter_tags(self):
        self.transactions.filter_tags(['Recurring'])
        self.assertEqual(len(self.transactions._df), 1)

    def test_add_row(self):
        # Skipping this test for now - need to review the method, re: classifications
        # self.process()
        # new_row = {
        #     'Date': pd.to_datetime('2023-01-03'),
        #     'Category': 'Utilities',
        #     'Description': 'Electric Bill',
        #     'Tags': None,
        #     'Comments': '',
        #     'Source': None,
        #     'Target': None,
        #     'Type': 'computed',
        #     'Distribution': None,
        #     'Amount': 300.0,
        #     'Sales Tax': 0.0,
        #     'Tips': 0.0
        # }
        # self.transactions.add_row(new_row, already_validated=True)
        # self.assertEqual(len(self.transactions._df), 3)
        pass

    def test_apply_labels(self):
        self.transactions.apply_labels()
        self.assertEqual(self.transactions._df.at[0, 'Source'], 'Income')
        self.assertEqual(self.transactions._df.at[0, 'Target'], 'Groceries')

    def test_process_rows(self):
        # Skipping this test for now - need to review the method, re: classifications
        # self.transactions.process_rows()
        # self.assertTrue(self.transactions.tips_processed)
        # self.assertTrue(self.transactions.sales_tax_processed)
        # self.assertTrue(self.transactions.surplus_deficit_processed)
        pass

    def test_collapse(self):
        self.transactions.collapse()
        # Add assertions based on expected behavior of collapse method

    def test_create_surplus_deficit_flows(self):
        self.transactions.create_surplus_deficit_flows()
        # Add assertions based on expected behavior of create_surplus_deficit_flows method

class TestDataRow(unittest.TestCase):

    def setUp(self):
        self.valid_data = [
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
        self.invalid_data = [
            pd.to_datetime('2023-01-01'),
            'Groceries',
            'Grocery Store',
            'food,essentials',
            'Monthly groceries',
            'Income',
            'Groceries',
            'computed',
            0,
            'invalid_amount',
            5.0,
            2.0,
            'Expense'
        ]

    def test_validate_valid_data(self):
        validated_data = DataRow.validate(self.valid_data, include_classifications=True)
        self.assertEqual(validated_data, self.valid_data)

    def test_validate_invalid_data(self):
        with self.assertRaises(Exception):
            DataRow.validate(self.invalid_data, include_classifications=True)

    def test_create_valid_data(self):
        created_data = DataRow.create(
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
        self.assertEqual(created_data, self.valid_data)

    def test_create_invalid_data(self):
        # with self.assertRaises(Exception):
        #     DataRow.create(
        #         date=pd.to_datetime('2023-01-01'),
        #         category_name='Groceries',
        #         source='Income',
        #         target='Groceries',
        #         amount='invalid_amount',
        #         description='Grocery Store',
        #         sales_tax=5.0,
        #         tips=2.0,
        #         comment='Monthly groceries',
        #         tags='food,essentials',
        #         row_type='computed',
        #         distribution=0,
        #         classification='Expense'
        #     )
        pass

    def test_tag_matches(self):
        row_tags = 'food,essentials'
        search_tags = ['food', 'luxury']
        matches = DataRow.tag_matches(row_tags, search_tags)
        self.assertEqual(matches, ['food'])

class TestIsNull(unittest.TestCase):

    def test_is_null_with_none(self):
        self.assertTrue(is_null(None))

    def test_is_null_with_nan(self):
        self.assertTrue(is_null(float('nan')))

    def test_is_null_with_nat(self):
        self.assertTrue(is_null(pd.NaT))

    def test_is_null_with_string_none(self):
        self.assertTrue(is_null("None"))

    def test_is_null_with_string_nan(self):
        self.assertTrue(is_null("NaN"))

    def test_is_null_with_string_null(self):
        self.assertTrue(is_null("null"))

    def test_is_null_with_empty_string(self):
        self.assertFalse(is_null(""))

    def test_is_null_with_zero(self):
        self.assertFalse(is_null(0))

    def test_is_null_with_valid_string(self):
        self.assertFalse(is_null("valid_string"))

    def test_is_null_with_valid_number(self):
        self.assertFalse(is_null(123))

    def test_is_null_with_valid_date(self):
        self.assertFalse(is_null(pd.Timestamp('2023-01-01')))

class TestIsEmpty(unittest.TestCase):

    def test_is_empty_with_none(self):
        self.assertTrue(is_empty(None))

    def test_is_empty_with_nan(self):
        self.assertTrue(is_empty(float('nan')))

    def test_is_empty_with_nat(self):
        self.assertTrue(is_empty(pd.NaT))

    def test_is_empty_with_string_none(self):
        self.assertTrue(is_empty("None"))

    def test_is_empty_with_string_nan(self):
        self.assertTrue(is_empty("NaN"))

    def test_is_empty_with_string_null(self):
        self.assertTrue(is_empty("null"))

    def test_is_empty_with_empty_string(self):
        self.assertTrue(is_empty(""))

    def test_is_empty_with_zero(self):
        self.assertFalse(is_empty(0))

    def test_is_empty_with_zero_nonzero_true(self):
        self.assertTrue(is_empty(0, nonzero=True))

    def test_is_empty_with_valid_string(self):
        self.assertFalse(is_empty("valid_string"))

    def test_is_empty_with_valid_number(self):
        self.assertFalse(is_empty(123))

    def test_is_empty_with_valid_date(self):
        self.assertFalse(is_empty(pd.Timestamp('2023-01-01')))

    def test_is_empty_with_nonzero_float(self):
        self.assertFalse(is_empty(0.25, nonzero=True))

    def test_is_empty_with_zero_float_nonzero_true(self):
        self.assertTrue(is_empty(0.0, nonzero=True))

    def test_is_empty_with_nonzero_float_nonzero_false(self):
        self.assertFalse(is_empty(0.25, nonzero=False))

    def test_is_empty_with_zero_float_nonzero_false(self):
        self.assertFalse(is_empty(0.0, nonzero=False))

    def test_is_empty_with_nonzero_int_nonzero_true(self):
        self.assertFalse(is_empty(1, nonzero=True))

    def test_is_empty_with_nonzero_int_nonzero_false(self):
        self.assertFalse(is_empty(1, nonzero=False))

    def test_is_empty_with_empty_list(self):
        self.assertFalse(is_empty([]))

    def test_is_empty_with_empty_dict(self):
        self.assertFalse(is_empty({}))

    def test_is_empty_with_empty_tuple(self):
        self.assertFalse(is_empty(()))

    def test_is_empty_with_empty_set(self):
        self.assertFalse(is_empty(set()))


class TestValidateDateString(unittest.TestCase):

    def test_valid_yyyy_mm_dd_format(self):
        self.assertTrue(validate_date_string("2023-01-01"))
        self.assertTrue(validate_date_string("1901-12-31"))
        self.assertTrue(validate_date_string("2099-01-01"))

    def test_valid_mm_dd_yyyy_format(self):
        self.assertTrue(validate_date_string("01/01/2023"))
        self.assertTrue(validate_date_string("12/31/1901"))
        self.assertTrue(validate_date_string("01/01/2099"))

    def test_invalid_year(self):
        self.assertFalse(validate_date_string("1899-12-31"))
        self.assertFalse(validate_date_string("2100-01-01"))
        self.assertFalse(validate_date_string("12/31/1899"))
        self.assertFalse(validate_date_string("01/01/2100"))

    def test_invalid_month(self):
        self.assertFalse(validate_date_string("2023-00-01"))
        self.assertFalse(validate_date_string("2023-13-01"))
        self.assertFalse(validate_date_string("00/01/2023"))
        self.assertFalse(validate_date_string("13/01/2023"))

    def test_invalid_day(self):
        self.assertFalse(validate_date_string("2023-01-00"))
        self.assertFalse(validate_date_string("2023-01-32"))
        self.assertFalse(validate_date_string("01/00/2023"))
        self.assertFalse(validate_date_string("01/32/2023"))

    def test_allow_empty(self):
        self.assertTrue(validate_date_string("", allow_empty=True))
        self.assertTrue(validate_date_string(None, allow_empty=True))

    def test_not_allow_empty(self):
        with self.assertRaises(Exception):
            self.assertFalse(validate_date_string("", allow_empty=False))
            self.assertFalse(validate_date_string(None, allow_empty=False))

    def test_invalid_format(self):
        self.assertFalse(validate_date_string("2023/01/01"))
        self.assertFalse(validate_date_string("01-01-2023"))
        self.assertFalse(validate_date_string("2023.01.01"))
        self.assertFalse(validate_date_string("01.01.2023"))

    def test_invalid_string(self):
        self.assertFalse(validate_date_string("invalid_date"))
        self.assertFalse(validate_date_string("2023-13-40"))
        self.assertFalse(validate_date_string("13/40/2023"))



if __name__ == '__main__':
    unittest.main()