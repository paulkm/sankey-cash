from pathlib import Path

import networkx as nx
import pytest

from sankey_cashflow.sankey_cash import RowLabels


class TestInit:

    def test_init(self, sample_row_labels):
        assert len(sample_row_labels.data) == 2
        assert 'House' in sample_row_labels._lookup
        assert 'Groceries' in sample_row_labels._lookup
        assert isinstance(sample_row_labels._digraph, nx.DiGraph)

    def test_missing_required_column_raises(self):
        with pytest.raises(Exception):
            RowLabels([{'Category Name': 'House', 'Type': 'computed'}])

    def test_duplicate_category_name_raises(self):
        row = {
            'Category Name': 'House', 'Type': 'computed', 'Source': 'Income', 'Target': 'House',
            'Classification': 'Expense', 'Link color': '', 'Node color': '', 'Comments': ''
        }
        with pytest.raises(Exception):
            RowLabels([row, dict(row)])

    def test_empty_category_name_is_skipped(self):
        row = {
            'Category Name': '', 'Type': '', 'Source': '', 'Target': '',
            'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''
        }
        labels = RowLabels([row])
        assert labels._lookup == {}

    def test_deductions_source_skips_dag_edge(self):
        row = {
            'Category Name': '401K', 'Type': '', 'Source': 'DEDUCTIONS', 'Target': '401K',
            'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''
        }
        labels = RowLabels([row])
        assert not labels._digraph.has_edge('DEDUCTIONS', '401K')
        assert '401K' in labels._lookup

    def test_s_tag_adds_node_not_edge(self):
        row = {
            'Category Name': 'Joe', 'Type': 's-tag', 'Source': '', 'Target': '',
            'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''
        }
        labels = RowLabels([row])
        assert labels._digraph.has_node('Joe')
        assert labels._digraph.nodes['Joe']['type'] == 's-tag'

    def test_tag_type_not_added_to_dag(self):
        row = {
            'Category Name': 'Ford', 'Type': 'tag', 'Source': 'Automotive', 'Target': 'Ford',
            'Classification': '', 'Link color': '', 'Node color': '', 'Comments': ''
        }
        labels = RowLabels([row])
        assert not labels._digraph.has_node('Ford')


class TestPaths:

    def test_get_longest_path(self, sample_row_labels):
        longest_path = sample_row_labels.get_longest_path()
        assert isinstance(longest_path, list)
        assert len(longest_path) >= 1

    def test_get_path(self, sample_row_labels):
        path = sample_row_labels.get_path('Income', 'House')
        assert isinstance(path, list)
        assert path == ['Income', 'House']

    def test_get_path_no_match_returns_none(self, sample_row_labels):
        assert sample_row_labels.get_path('House', 'Income') is None


class TestLabelLookup:

    def test_get_label(self, sample_row_labels):
        label = sample_row_labels.get_label('House')
        assert label is not None
        assert label['source'] == 'Income'
        assert label['target'] == 'House'

    def test_get_label_unknown_returns_none(self, sample_row_labels):
        assert sample_row_labels.get_label('Nonexistent') is None

    def test_get_attribute(self, sample_row_labels):
        assert sample_row_labels.get_attribute('House', 'source') == 'Income'
        assert sample_row_labels.get_attribute('House', 'target') == 'House'
        assert sample_row_labels.get_attribute('House', 'classification') == 'Expense'

    def test_get_attribute_unknown_attribute_raises(self, sample_row_labels):
        with pytest.raises(Exception):
            sample_row_labels.get_attribute('House', 'not_a_real_attribute')

    def test_get_attribute_missing_label_uses_default(self, sample_row_labels):
        source = sample_row_labels.get_attribute('Nonexistent', 'source')
        assert source == 'Uncategorized'
        target = sample_row_labels.get_attribute('Nonexistent', 'target')
        assert target == 'Nonexistent'

    def test_get_attribute_missing_label_no_default_returns_none(self, sample_row_labels):
        assert sample_row_labels.get_attribute('Nonexistent', 'source', use_default=False) is None


class TestPrintGraph:

    def test_print_graph_writes_file(self, sample_row_labels, tmp_path):
        out_file = tmp_path / 'test_graph.png'
        sample_row_labels.print_graph(str(out_file))
        assert out_file.is_file()
