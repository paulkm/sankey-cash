"""
sankey-cash: transforms columnar transaction data (CSV or Google Sheets) into cashflow graph
data, and renders it as a Sankey diagram or a line chart via plotly.

See README.md for usage instructions and examples.

References:
- https://lifewithdata.com/2022/08/29/how-to-create-a-sankey-diagram-in-plotly-python/
- https://erikrood.com/Posts/py_gsheets.html
- https://github.com/nithinmurali/pygsheets
- https://pygsheets.readthedocs.io/en/stable/
- https://plotly.com/python/sankey-diagram/

Notes:
- Permissions: Create a service account and download credentials in json format
  (detailed instructions here: https://pygsheets.readthedocs.io/en/stable/authorization.html),
  then share the spreadsheet with the service account user.
"""

from .data_row import DataRow
from .diagram import build_line_figure, build_sankey_figure
from .io import fetch_data, read_csv_as_df, read_gsheet_as_df
from .labels import RowLabels
from .settings import AppSettings
from .transactions import Transactions
from .utils import (
    df_date_filter,
    is_empty,
    is_null,
    normalize_amounts,
    save_report,
    validate_date_string,
)

__all__ = [
    "AppSettings",
    "RowLabels",
    "Transactions",
    "DataRow",
    "fetch_data",
    "read_csv_as_df",
    "read_gsheet_as_df",
    "build_sankey_figure",
    "build_line_figure",
    "is_null",
    "is_empty",
    "df_date_filter",
    "save_report",
    "validate_date_string",
    "normalize_amounts",
]
