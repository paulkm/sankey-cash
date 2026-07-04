import pandas as pd
import pytest

from sankey_cashflow import RowLabels, Transactions


class TestInit:

    def test_init(self, sample_transactions):
        assert sample_transactions.length == 2
        assert sample_transactions.earliest_date == pd.to_datetime('2023-01-01')
        assert sample_transactions.latest_date == pd.to_datetime('2023-01-02')

    def test_validate_df(self, sample_transactions):
        assert sample_transactions._validate_df() is True

    def test_init_raises_on_non_float_amount(self, make_transactions_df, sample_row_labels, default_app_settings):
        df = make_transactions_df([
            {'Date': '2023-01-01', 'Category': 'Groceries', 'Amount': '40.00'},
        ])
        with pytest.raises(Exception):
            Transactions(df, sample_row_labels, default_app_settings)


class TestAudit:

    def test_audit_no_missing_transactions(self, sample_transactions):
        audit_data = pd.DataFrame({
            'Date': [pd.to_datetime('2023-01-01')],
            'Amount': [107],
            'Description': ['Grocery Store']
        })
        assert sample_transactions.audit(audit_data) == ""

    def test_audit_reports_missing_transaction(self, sample_transactions):
        audit_data = pd.DataFrame({
            'Date': [pd.to_datetime('2023-06-01')],
            'Amount': [9999],
            'Description': ['Unknown Charge']
        })
        report = sample_transactions.audit(audit_data)
        assert 'Unknown Charge' in report


class TestFilterTags:

    def test_filter_tags_drops_matching_rows(self, sample_transactions):
        sample_transactions.filter_tags(['Recurring'])
        assert len(sample_transactions._df) == 1
        assert 'Recurring' not in sample_transactions._df['Tags'].tolist()

    def test_filter_tags_no_match_is_noop(self, sample_transactions):
        sample_transactions.filter_tags(['NoSuchTag'])
        assert len(sample_transactions._df) == 2


class TestApplyLabelsBasic:

    def test_apply_labels_resolves_default_source_target(self, sample_transactions):
        sample_transactions.apply_labels()
        assert sample_transactions._df.at[0, 'Source'] == 'Income'
        assert sample_transactions._df.at[0, 'Target'] == 'Groceries'


@pytest.fixture
def tag_labels_data():
    return [
        {'Category Name': 'Food', 'Type': 'computed', 'Source': 'Income', 'Target': 'Food',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        {'Category Name': 'Coffee Shops', 'Type': '', 'Source': 'Food', 'Target': 'Eating Out',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        {'Category Name': 'Ford', 'Type': 'tag', 'Source': 'Automotive', 'Target': 'Ford',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        {'Category Name': 'Automotive', 'Type': 'computed', 'Source': 'Income', 'Target': 'Automotive',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        {'Category Name': 'Gas', 'Type': '', 'Source': 'Automotive', 'Target': 'Gas',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        {'Category Name': 'Joe', 'Type': 's-tag', 'Source': '', 'Target': '',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        {'Category Name': 'House', 'Type': 'computed', 'Source': 'Income', 'Target': 'House',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        {'Category Name': '401K', 'Type': '', 'Source': 'DEDUCTIONS', 'Target': '401K',
         'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
    ]


@pytest.fixture
def tag_row_labels(tag_labels_data):
    return RowLabels(tag_labels_data)


def _transactions_for(df_rows, row_labels, make_transactions_df, make_args, **settings_overrides):
    from sankey_cashflow import AppSettings
    df = make_transactions_df(df_rows)
    settings = AppSettings(make_args(**settings_overrides))
    return Transactions(df, row_labels, settings)


class TestApplyLabelsTagBranches:

    def test_tag_append_mode(self, tag_row_labels, make_transactions_df, make_args):
        # 'Weekend' is not defined in the labels sheet at all (not a 'tag' or 's-tag' type row),
        # so this exercises the plain append branch rather than s-tag/tag_override handling.
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Coffee Shops', 'Tags': 'Weekend', 'Amount': 10.0}],
            tag_row_labels, make_transactions_df, make_args, tags='Weekend'
        )
        txn.apply_labels()
        assert txn._df.at[0, 'Source'] == 'Eating Out'
        assert txn._df.at[0, 'Target'] == 'Weekend'

    def test_tag_override_matched(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Tags': 'Ford', 'Amount': 10.0}],
            tag_row_labels, make_transactions_df, make_args, tags='Ford', tag_override=True
        )
        txn.apply_labels()
        assert txn._df.at[0, 'Source'] == 'Automotive'
        assert txn._df.at[0, 'Target'] == 'Ford'

    def test_tag_override_unmatched_falls_back_to_income(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Coffee Shops', 'Tags': 'Mystery', 'Amount': 10.0}],
            tag_row_labels, make_transactions_df, make_args, tags='Mystery', tag_override=True
        )
        txn.apply_labels()
        assert txn._df.at[0, 'Source'] == 'Income'
        assert txn._df.at[0, 'Target'] == 'Mystery'

    def test_s_tag_redirects_income_source(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'House', 'Tags': 'Joe', 'Amount': 10.0}],
            tag_row_labels, make_transactions_df, make_args, tags='Joe'
        )
        txn.apply_labels()
        assert txn._df.at[0, 'Source'] == 'Joe'
        assert txn._df.at[0, 'Target'] == 'House'

    def test_store_match(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Description': 'Costco', 'Amount': 10.0}],
            tag_row_labels, make_transactions_df, make_args, stores='Costco'
        )
        txn.apply_labels()
        assert txn._df.at[0, 'Source'] == 'Gas'
        assert txn._df.at[0, 'Target'] == 'Costco'

    def test_recurring_redirects_income_source(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'House', 'Amount': 10.0}],
            tag_row_labels, make_transactions_df, make_args, recurring=True
        )
        txn.apply_labels()
        assert txn._df.at[0, 'Source'] == 'Recurring'
        assert txn._df.at[0, 'Target'] == 'House'
        assert txn._labels_obj._digraph.has_edge('Income', 'Recurring')

    def test_deductions_source_uses_description(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': '401K', 'Description': 'Employer', 'Amount': 10.0}],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.apply_labels()
        assert txn._df.at[0, 'Source'] == 'Employer'
        assert txn._df.at[0, 'Target'] == '401K'
        assert txn._df.at[0, 'Type'] == 'deduction'

    def test_orphan_edge_raises(self, make_transactions_df, make_args):
        placeholder = [{'Category Name': 'default', 'Type': 'default', 'Source': '', 'Target': '',
                        'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''}]
        isolated_labels = RowLabels(placeholder)
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Mystery Category', 'Amount': 10.0}],
            isolated_labels, make_transactions_df, make_args
        )
        with pytest.raises(Exception):
            txn.apply_labels()


class TestProcessRows:

    def test_sales_tax_creates_synthetic_row_and_updates_amount(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 40.0, 'Sales Tax': 1.5}],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.apply_labels()
        txn.process_rows()
        tax_rows = txn._df[txn._df['Target'] == 'Sales Tax']
        assert len(tax_rows) == 1
        assert tax_rows.iloc[0]['Amount'] == 1.5
        assert tax_rows.iloc[0]['Source'] == 'Gas'
        assert txn._df.at[0, 'Amount'] == 41.5

    def test_separate_taxes_routes_from_income(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 40.0, 'Sales Tax': 1.5}],
            tag_row_labels, make_transactions_df, make_args, separate_tax=True
        )
        txn.apply_labels()
        txn.process_rows()
        tax_rows = txn._df[txn._df['Target'] == 'Sales Tax']
        assert len(tax_rows) == 1
        assert tax_rows.iloc[0]['Source'] == 'Income'
        # Original amount is untouched when taxes are kept separate
        assert txn._df.at[0, 'Amount'] == 40.0

    def test_tips_creates_synthetic_row_and_updates_amount(self, tag_row_labels, make_transactions_df, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 40.0, 'Tips': 5.0}],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.apply_labels()
        txn.process_rows()
        tip_rows = txn._df[txn._df['Target'] == 'Tips']
        assert len(tip_rows) == 1
        assert tip_rows.iloc[0]['Amount'] == 5.0
        assert txn._df.at[0, 'Amount'] == 45.0

    def test_multi_hop_dag_creates_synthetic_intermediate_row(self, make_transactions_df, make_args):
        labels_data = [
            {'Category Name': 'House', 'Type': 'computed', 'Source': 'Income', 'Target': 'House',
             'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
            {'Category Name': 'Mortgage', 'Type': '', 'Source': 'House', 'Target': 'Mortgage',
             'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''},
        ]
        row_labels = RowLabels(labels_data)
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Mortgage', 'Amount': 1500.0}],
            row_labels, make_transactions_df, make_args
        )
        txn.apply_labels()
        txn.process_rows()
        synthetic = txn._df[(txn._df['Source'] == 'Income') & (txn._df['Target'] == 'House')]
        assert len(synthetic) == 1
        assert synthetic.iloc[0]['Amount'] == 1500.0


class TestCollapse:

    def test_collapse_aggregates_shared_pairs(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [
                {'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 40.0, 'Source': 'Automotive', 'Target': 'Gas'},
                {'Date': '2023-01-05', 'Category': 'Gas', 'Amount': 25.0, 'Source': 'Automotive', 'Target': 'Gas'},
            ],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.collapse()
        grouped = txn._grouped_df
        assert len(grouped) == 1
        assert grouped.iloc[0]['Amount'] == 65.0


class TestSurplusDeficit:

    def test_income_surplus(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [
                {'Date': '2023-01-01', 'Category': 'Salary', 'Amount': 1000.0, 'Source': 'Job', 'Target': 'Income'},
                {'Date': '2023-01-02', 'Category': 'Gas', 'Amount': 400.0, 'Source': 'Income', 'Target': 'Gas'},
            ],
            tag_row_labels, make_transactions_df, make_args
        )
        # In real usage this column is created by apply_labels(), which always runs before this
        # method in Transactions.process(). Set it directly to unit test this method in isolation.
        txn._df['Classification'] = 'Uncategorized'
        txn.create_surplus_deficit_flows()
        surplus_rows = txn._df[txn._df['Target'] == 'Income Surplus']
        assert len(surplus_rows) == 1
        assert surplus_rows.iloc[0]['Amount'] == 600.0
        assert surplus_rows.iloc[0]['Source'] == 'Income'

    def test_income_deficit(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [
                {'Date': '2023-01-01', 'Category': 'Salary', 'Amount': 400.0, 'Source': 'Job', 'Target': 'Income'},
                {'Date': '2023-01-02', 'Category': 'Gas', 'Amount': 1000.0, 'Source': 'Income', 'Target': 'Gas'},
            ],
            tag_row_labels, make_transactions_df, make_args
        )
        # In real usage this column is created by apply_labels(), which always runs before this
        # method in Transactions.process(). Set it directly to unit test this method in isolation.
        txn._df['Classification'] = 'Uncategorized'
        txn.create_surplus_deficit_flows()
        deficit_rows = txn._df[txn._df['Source'] == 'Income Deficit']
        assert len(deficit_rows) == 1
        assert deficit_rows.iloc[0]['Amount'] == 600.0
        assert deficit_rows.iloc[0]['Target'] == 'Income'

    def test_s_tag_surplus_kept_separate_by_default(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [
                {'Date': '2023-01-01', 'Category': 'Salary', 'Amount': 500.0, 'Source': 'Job', 'Target': 'Joe'},
                {'Date': '2023-01-02', 'Category': 'Gas', 'Amount': 200.0, 'Source': 'Joe', 'Target': 'Gas'},
            ],
            tag_row_labels, make_transactions_df, make_args
        )
        # In real usage this column is created by apply_labels(), which always runs before this
        # method in Transactions.process(). Set it directly to unit test this method in isolation.
        txn._df['Classification'] = 'Uncategorized'
        txn.create_surplus_deficit_flows()
        surplus_rows = txn._df[txn._df['Target'] == 'Joe Surplus']
        assert len(surplus_rows) == 1
        assert surplus_rows.iloc[0]['Amount'] == 300.0
        assert surplus_rows.iloc[0]['Source'] == 'Joe'

    def test_s_tag_surplus_feeds_back_to_income(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [
                {'Date': '2023-01-01', 'Category': 'Salary', 'Amount': 500.0, 'Source': 'Job', 'Target': 'Joe'},
                {'Date': '2023-01-02', 'Category': 'Gas', 'Amount': 200.0, 'Source': 'Joe', 'Target': 'Gas'},
            ],
            tag_row_labels, make_transactions_df, make_args, feed_in=True, tags='Joe'
        )
        txn._df['Classification'] = 'Uncategorized'
        txn.create_surplus_deficit_flows()
        surplus_rows = txn._df[(txn._df['Source'] == 'Joe') & (txn._df['Target'] == 'Income')]
        assert len(surplus_rows) == 1
        assert surplus_rows.iloc[0]['Amount'] == 300.0


class TestFilterDates:

    @pytest.fixture
    def dated_transactions(self, make_transactions_df, tag_row_labels, make_args):
        return _transactions_for(
            [
                {'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 10.0},
                {'Date': '2023-02-01', 'Category': 'Gas', 'Amount': 20.0},
                {'Date': '2023-03-01', 'Category': 'Gas', 'Amount': 30.0},
                {'Date': '2023-04-01', 'Category': 'Gas', 'Amount': 40.0},
            ],
            tag_row_labels, make_transactions_df, make_args
        )

    def test_filters_to_inclusive_range(self, dated_transactions):
        dated_transactions.filter_dates('2023-02-01', '2023-03-01')
        assert len(dated_transactions._df) == 2
        assert dated_transactions.earliest_date == pd.to_datetime('2023-02-01')
        assert dated_transactions.latest_date == pd.to_datetime('2023-03-01')

    def test_none_none_is_noop(self, dated_transactions):
        dated_transactions.filter_dates(None, None)
        assert len(dated_transactions._df) == 4

    def test_open_ended_start_uses_earliest(self, dated_transactions):
        dated_transactions.filter_dates(None, '2023-02-01')
        assert len(dated_transactions._df) == 2

    def test_start_after_end_raises(self, dated_transactions):
        with pytest.raises(Exception):
            dated_transactions.filter_dates('2023-04-01', '2023-01-01')

    def test_empty_result_raises(self, dated_transactions):
        with pytest.raises(Exception):
            dated_transactions.filter_dates('2024-01-01', '2024-02-01')


class TestDistributeAmounts:
    """
    In Transactions.process(), distribute_amounts() (step 2) always runs BEFORE apply_labels()
    (step 4), so the "Classification" column apply_labels() creates does not exist yet at this
    point in real usage. These tests deliberately do NOT pre-create that column, matching real
    call order - this is a regression test for a bug where distribute_amounts() crashed
    unconditionally whenever a distributed row was processed before apply_labels() had run.
    """

    def test_forward_distribution_splits_amount_and_dates(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 120.0, 'Distribution': 3}],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.distribute_amounts()
        assert len(txn._df) == 3
        assert all(txn._df['Amount'] == 40.0)
        dates = sorted(txn._df['Date'].tolist())
        assert dates[0] == pd.to_datetime('2023-01-01')
        assert dates[1] > dates[0]
        assert dates[2] > dates[1]

    def test_reverse_distribution_moves_dates_backward(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [{'Date': '2023-03-01', 'Category': 'Gas', 'Amount': 90.0, 'Distribution': -3}],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.distribute_amounts()
        assert len(txn._df) == 3
        dates = txn._df['Date'].tolist()
        assert min(dates) < pd.to_datetime('2023-03-01')

    def test_sales_tax_distributed_alongside_amount(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 120.0, 'Distribution': 3, 'Sales Tax': 12.0}],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.distribute_amounts()
        assert all(txn._df['Sales Tax'] == 4.0)

    def test_calling_twice_is_noop(self, make_transactions_df, tag_row_labels, make_args):
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 120.0, 'Distribution': 3}],
            tag_row_labels, make_transactions_df, make_args
        )
        txn.distribute_amounts()
        assert len(txn._df) == 3
        txn.distribute_amounts()
        assert len(txn._df) == 3

    def test_distribution_before_apply_labels_does_not_crash(self, make_transactions_df, tag_row_labels, make_args):
        # Regression test matching the real Transactions.process() call order: distribute_amounts()
        # before apply_labels(), with no "Classification" column present yet on either the original
        # or the synthetic rows it creates.
        txn = _transactions_for(
            [{'Date': '2023-01-01', 'Category': 'Gas', 'Amount': 90.0, 'Distribution': 3}],
            tag_row_labels, make_transactions_df, make_args
        )
        assert 'Classification' not in txn._df.columns
        txn.distribute_amounts()
        assert 'Classification' not in txn._df.columns
        assert len(txn._df) == 3
        txn.apply_labels()
        assert 'Classification' in txn._df.columns
        assert all(txn._df['Classification'].notna())

    def test_no_distribution_rows_untouched(self, sample_transactions):
        original_len = len(sample_transactions._df)
        sample_transactions.distribute_amounts()
        assert len(sample_transactions._df) == original_len


class TestFullProcessPipeline:

    def test_process_marks_surplus_deficit_processed(self, sample_transactions):
        sample_transactions.process()
        assert sample_transactions.surplus_deficit_processed is True
        assert sample_transactions._grouped_df is not None
