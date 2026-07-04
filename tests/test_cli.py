import pytest

import sankey_cashflow.cli as cli_module
from sankey_cashflow.cli import build_arg_parser


class TestBuildArgParser:

    def test_defaults(self):
        args = build_arg_parser().parse_args([])
        assert args.source is None
        assert args.sheet is None
        assert args.srcmap is None
        assert args.range is False
        assert args.separate_tax is False
        assert args.verbose is False
        assert args.creds is None
        assert args.distributions is False
        assert args.tags is None
        assert args.exclude is None
        assert args.tag_override is False
        assert args.stores is None
        assert args.all_time is False
        assert args.feed_in is False
        assert args.audit is False
        assert args.recurring is False
        assert args.hover is None
        assert args.dtype is None

    def test_parses_source_and_srcmap(self):
        args = build_arg_parser().parse_args(['-s', 'data.csv', '--srcmap', 'labels.csv'])
        assert args.source == 'data.csv'
        assert args.srcmap == 'labels.csv'

    def test_parses_store_true_flags(self):
        args = build_arg_parser().parse_args([
            '-r', '--separate_tax', '-v', '--distributions', '--tag_override',
            '--all_time', '--feed_in', '--audit', '--recurring'
        ])
        assert args.range is True
        assert args.separate_tax is True
        assert args.verbose is True
        assert args.distributions is True
        assert args.tag_override is True
        assert args.all_time is True
        assert args.feed_in is True
        assert args.audit is True
        assert args.recurring is True

    def test_parses_string_options(self):
        args = build_arg_parser().parse_args([
            '--tags', 'Ford, Dodge', '--exclude', 'Onetime', '--stores', "Trader Joe's",
            '--hover', 'Description', '--dtype', 'line', '--creds', 'creds.json', '-t', 'Sheet1'
        ])
        assert args.tags == 'Ford, Dodge'
        assert args.exclude == 'Onetime'
        assert args.stores == "Trader Joe's"
        assert args.hover == 'Description'
        assert args.dtype == 'line'
        assert args.creds == 'creds.json'
        assert args.sheet == 'Sheet1'


class TestMainEndToEnd:
    """
    Integration tests driving cli.main() the same way the installed `sankeyd` command would,
    against sample_data/. save_report() and Figure.show() are stubbed out so tests don't write
    report files into the repo or try to open a browser.
    """

    def test_main_runs_sankey_pipeline(self, monkeypatch):
        monkeypatch.setattr(cli_module, 'save_report', lambda *a, **kw: None)
        shown = []
        monkeypatch.setattr('plotly.graph_objects.Figure.show', lambda self, *a, **kw: shown.append(True))
        cli_module.main([
            '--source', 'sample_data/expenses.csv', '--srcmap', 'sample_data/labels.csv', '--all_time'
        ])
        assert shown == [True]

    def test_main_runs_line_pipeline(self, monkeypatch):
        monkeypatch.setattr(cli_module, 'save_report', lambda *a, **kw: None)
        monkeypatch.setattr('builtins.input', lambda *a, **kw: 'week')
        shown = []
        monkeypatch.setattr('plotly.graph_objects.Figure.show', lambda self, *a, **kw: shown.append(True))
        cli_module.main([
            '--source', 'sample_data/expenses.csv', '--srcmap', 'sample_data/labels.csv', '--all_time',
            '--dtype', 'line'
        ])
        assert shown == [True]

    def test_main_audit_mode_exits_without_generating_diagram(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cli_module, 'save_report', lambda *a, **kw: None)
        audit_csv = tmp_path / 'bank.csv'
        audit_csv.write_text('Date,Amount,Description\n1/1/23,-4000.00,Boeing\n')
        monkeypatch.setattr('builtins.input', lambda *a, **kw: str(audit_csv))
        shown = []
        monkeypatch.setattr('plotly.graph_objects.Figure.show', lambda self, *a, **kw: shown.append(True))
        with pytest.raises(SystemExit):
            cli_module.main([
                '--source', 'sample_data/expenses.csv', '--srcmap', 'sample_data/labels.csv',
                '--all_time', '--audit'
            ])
        assert shown == []

    def test_main_invalid_source_raises(self):
        # Fails during AppSettings construction/validation, before any fetch_data() call -
        # this is a plain Exception, not the SystemExit that fetch_data()'s own failure path raises.
        with pytest.raises(Exception):
            cli_module.main(['--source', 'does_not_exist.csv'])
