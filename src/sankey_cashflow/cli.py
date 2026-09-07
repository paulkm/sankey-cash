import argparse
import datetime

import pandas as pd

from .diagram import build_sankey_figure, build_scatter_figure, build_trend_figure
from .io import fetch_data, read_csv_as_df
from .labels import RowLabels
from .settings import AppSettings
from .transactions import Transactions
from .utils import logger, save_report, validate_date_string


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sankeyd", description="Generate a cashflow Sankey or line diagram.")
    parser.add_argument("-s", "--source", help="Data source, either a Google sheet or a .csv")
    parser.add_argument("-t", "--sheet", help="Sheet name, defaults to 'current_exp'")
    parser.add_argument("--srcmap", help="Location for sources-targets mapping csv (only needed for csv data "
                        "sources). Defaults to 'Sources-Targets' for GSheets")
    parser.add_argument("-r", "--range", help="Enable time range filtering", action="store_true")
    parser.add_argument("--separate_tax", help="Show taxes as own flow", action="store_true")
    parser.add_argument("-v", "--verbose", help="Enable verbose output", action="store_true")
    # Note: the specified service account needs to have access to the data source document.
    parser.add_argument("--creds", help="Google service account credentials to use (in json format).")
    parser.add_argument("--distributions", help="Distribute transactions where noted", action="store_true")
    parser.add_argument("--tags", help="Comma delimited list of tags to search for, eg 'foo, bar, baz bat'.")
    parser.add_argument("--exclude", help="Comma delimited list of tags to exclude, eg 'foo, bar, baz bat'.")
    parser.add_argument("--tag_override", action="store_true",
                        help="Use tag labels to override source/targets instead of appending.")
    parser.add_argument("--stores", help="Comma delimited list of stores/payees to override source-targets on, "
                        "eg 'Safeway, Bartells, Fred Meyer'.")
    parser.add_argument("--all_time", action="store_true",
                        help="Include transactions that happen in the future and before 10/1/2022")
    parser.add_argument("--feed_in", help="If using source-tags, feed surplus into income.", action="store_true")
    parser.add_argument("--audit", help="Audit source data transactions for missing items", action="store_true")
    parser.add_argument("--recurring", help="Split recurring expenses out", action="store_true")
    parser.add_argument("--hover", help="Grouping field for hover text. Defaults to 'Category'")
    parser.add_argument("--dtype", help="Diagram type to generate (sankey, trend, scatter). Defaults to 'sankey'")
    parser.add_argument("--resolution", help="Chart resolution for the trend diagram type: day, week, month, "
                        "quarter, year, or an explicit multiple like '3 months'. Defaults to 'week'")
    parser.add_argument("--trend-mode", dest="trend_mode",
                        help="Trend diagram Y-axis mode: 'percent' (deviation from each classification's own "
                        "baseline, comparable across differently-sized categories) or 'dollars' (raw amounts, "
                        "best for a single classification). Defaults to 'percent'.")
    parser.add_argument("--trend-baseline", dest="trend_baseline",
                        help="Baseline strategy used by trend --trend-mode=percent (mean, median, trimmed-mean). "
                        "Defaults to 'trimmed-mean'.")
    parser.add_argument("--trend-trim", dest="trend_trim",
                        help="Percent to trim from each end (highest/lowest datapoints) before averaging, when "
                        "--trend-baseline=trimmed-mean. Defaults to 5.")
    parser.add_argument("--trend-category", dest="trend_category",
                        help="Comma delimited list of Classifications to restrict the trend diagram to, eg "
                        "'Housing Exp, Auto'. Defaults to all (non-hidden) classifications.")
    parser.add_argument("--trend-outlier-tag", dest="trend_outlier_tag",
                        help="Tag used to manually exclude a transaction from trend analysis entirely (baseline "
                        "and plotted values). Defaults to 'Outlier'.")
    parser.add_argument("--scatter-smoothing", dest="scatter_smoothing",
                        help="Smoothing method for the scatter diagram type: 'lowess' or 'moving-average'. "
                        "Defaults to 'lowess'.")
    parser.add_argument("--scatter-lowess-frac", dest="scatter_lowess_frac",
                        help="LOWESS smoothing fraction in (0, 1], used when --scatter-smoothing=lowess. "
                        "Defaults to 0.3.")
    parser.add_argument("--scatter-ma-window", dest="scatter_ma_window",
                        help="Moving-average window, used when --scatter-smoothing=moving-average. Same syntax "
                        "as --resolution (day, week, month, quarter, year, or an explicit multiple like "
                        "'3 months'). Defaults to 'month'.")
    return parser


def _prompt_for_date_range(app_settings) -> tuple:
    sdate = input("Enter start date, in form of YYYY-MM-DD or MM/DD/YYYY. (<Enter> to leave unbounded): ")
    while not validate_date_string(sdate, True):
        sdate = input(f"Invalid date string ({sdate})! Please enter start date, in form of YYYY-MM-DD or "
                      "MM/DD/YYYY. (<Enter> to leave unbounded): ")
    edate = input("Enter end date, in form of YYYY-MM-DD. (<Enter> to leave unbounded): ")
    if not edate:
        edate = datetime.datetime.now().strftime("%Y-%m-%d")
    while not validate_date_string(edate, True):
        edate = input(f"Invalid date string ({edate})! Please enter end date, in form of YYYY-MM-DD or "
                      "MM/DD/YYYY. (<Enter> to leave unbounded): ")
    try:
        app_settings.date_filter_start = sdate
        app_settings.date_filter_end = edate
        if app_settings.date_filter_start is None and app_settings.date_filter_end is None:
            print("Need to have at least one of start date or end date to use date filtering!")
            raise SystemExit(1)
    except Exception as e:
        print(f"Could not parse supplied date(s). Error was: {e}")
        raise SystemExit(1)
    return sdate, edate


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    app_settings = AppSettings(args)

    date_range = None
    if app_settings.filter_dates:
        # Doing this first, as it involves user input - throw any errors related to that before fetching data.
        date_range = _prompt_for_date_range(app_settings)

    if app_settings.verbose:
        logger.info(f"Fetching data from {app_settings.data_source}: {app_settings.data_sheet}...")
    src_target, df = fetch_data(app_settings)

    sources_targets = RowLabels(src_target)
    transactions_data = Transactions(df, sources_targets, app_settings)

    save_report(sources_targets.process_report, 'labels_report')

    if app_settings.audit_mode:
        print("We are in audit mode, so we will not process the data.")
        audit_file = input("Enter the path to the bank transactions file: ")
        audit_data = read_csv_as_df(audit_file)
        audit_data["Date"] = pd.to_datetime(audit_data["Date"])  # Normalize date format
        audit_data["Amount"] = audit_data["Amount"].apply(lambda x: x * -1)  # Convert from negative to positive
        audit_report = transactions_data.audit(audit_data, date_range)
        print(audit_report)
        raise SystemExit

    if app_settings.diagram_type == 'sankey':
        transactions_data.process(date_range)
    elif app_settings.diagram_type in ('trend', 'scatter'):
        transactions_data.process_trend(date_range)
    else:
        print(f"Invalid diagram type: {app_settings.diagram_type}")
        raise SystemExit(1)

    save_report(transactions_data.process_report, 'transactions_report')

    if app_settings.verbose:
        logger.info(f"Generating diagram of type {app_settings.diagram_type}")

    if app_settings.diagram_type == 'sankey':
        fig = build_sankey_figure(transactions_data, sources_targets, app_settings)
    elif app_settings.diagram_type == 'trend':
        fig = build_trend_figure(transactions_data, app_settings)
    else:
        fig = build_scatter_figure(transactions_data, app_settings)
    fig.show()


if __name__ == '__main__':
    main()
