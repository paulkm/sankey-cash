# Sankey diagram generator for cashflow

## Information
Turns columnar transaction data (a CSV or Google Sheet) into a configurable Sankey diagram or
line chart of cashflow, via the `sankeyd` command line tool. The underlying classes are also
importable directly if you want to build your own pipeline or diagram.
[![Test coverage](https://paulkm.github.io/sankey-cash/coverage-badge.svg?raw=true)](https://paulkm.github.io/sankey-cash/)

## Installation
- `pip install sankey-cash`
- From testpy: `python3 -m pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple sankey-cash`

## Dev/test install
- `git clone git@github.com:paulkm/sankey-cash.git`
- `cd sankey-cash`
- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -e ".[test]"`
- Create a service account using the instructions here: https://pygsheets.readthedocs.io/en/stable/authorization.html and copy the downloaded credentials.json file to the project directory as 'google_service_account_key.json' or by calling sankeyd using the `--creds` arg pointing to the location of your credentials file.

## Running
- `sankeyd --help`
- `sankeyd -s <name of a Google Sheets document> -t <worksheet name for transactions> --srcmap <worksheet name for sources-targets> --creds <location of service account credentials file>`
    - `-t`, `--srcmap`, and `--creds` are all optional and if omitted will default to `'current_exp'`, `'Sources-Targets'`, and `'./google_service_account_key.json'` respectively.
- `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' -r` (date range arg is necessary since sample data is older - use 1/1/2021 as start date and 12/31/2021 as end date, or pass `--all_time` to skip the prompt)
- `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --all_time --dtype=line`

### Library usage
If you want to build your own pipeline instead of using `sankeyd` directly:
```python
from sankey_cashflow import AppSettings, RowLabels, Transactions, fetch_data, build_sankey_figure

app_settings = AppSettings(args)  # args: anything with the same attributes argparse would give sankeyd
src_target, df = fetch_data(app_settings)
labels = RowLabels(src_target)
transactions = Transactions(df, labels, app_settings)
transactions.process()
fig = build_sankey_figure(transactions, labels, app_settings)
fig.show()
```

## Data prerequisites
Two sheets are needed, either in a Google Sheets workbook or as two CSV files. See sample_data directory for example data.

### Labels (sources-targets)
The following columns, in this order, are required:
- Category Name
    - Required & unique. Name to match transactions with. Case-sensitive.
- Type
    - Optional. Allowed values:
        - computed. Indicates a 'intermediate' node for longer flows, eg "Income" -> "Household".
        - tag. Indicates a label that would only be used during tag overrides. Ignored for normal lookups.
        - s-tag. Indicates a special "Source tag". See notes on tag handling below for usage.
- Source
    - Optional. Source node for any transaction matching this category. If not specified, label will only be used for color lookups.
- Target
    - Optional. Source node for any transaction matching this category. If not specified, label will only be used for color lookups.
- Classification
    - Optional. Free text grouping used by the line-chart diagram type (`--dtype line`) to group flows - eg several categories might share a "Housing Exp" classification. Prefix a classification with `x` (eg `xEntertainment`) to hide it from line charts by default. Not used by the Sankey diagram type.
- Link color
    - Optional. RGB+Alpha value as string, eg: 'rgba(179, 204, 230, 0.8)'
- Node color
    - Optional. RGB+Alpha value as string, eg: 'rgba(179, 204, 230, 1.0)'
- Comments
    - Optional. Free text.

### Expenses data
The following columns, in this order, are required. For optional values, an empty string can be used:
- Date
  - Required. String value. Date values in US format, eg: MM/DD/YYYY. Note: datetime conversions will attempt to resolve different date strings correctly.
- Category
  - Required. String value. Should map to a category name in the sources-targets spreadsheet. If not mapped, will go to 'Uncategorized > category name'.
- Description
  - Required. String value. Typically, the payee/payor name. Used for grouping transactions by store.
- Tags
  - Optional. String value. Comma-delimited list of tags to use for grouping operations.
- Comments
  - Optional. String value.
- Source
  - Optional. String value. Can be used to override source-target assignments if desired.
- Target
  - Optional. String value. Can be used to override source-target assignments if desired.
- Type
  - Not used in your source data - leave blank. The library populates this internally to track computed/synthetic/deduction rows during processing.
- Distribution
  - Optional. Integer value. Used to distribute the amount over n number of months. If used, the actual transaction month will be the first month, with n-1 number of synthetic transactions to follow.
- Amount
  - Required. String or float value. Amount in US$ for the transaction. If a string value should look like "$x,xxx.xx"
- Sales Tax
  - Optional. String or float value. Amount in US$ for the transaction sales tax. If a string value should look like "$x,xxx.xx". Note: if used, the value in the amount column should NOT include sales tax.
- Tips
  - Optional. String or float value. Amount in US$ for tip. If a string value should look like "$x,xxx.xx". Note: if used, the value in the amount column should NOT include tip.

## Usage notes
- All data rows are positive values with the labels sheet controlling whether they flow into or out of the "Income" node. (all income types flow in, all expenses flow out).
- The labels sheet is used to map particular categories to a source-target pair (eg, you might combine anything categorized as 'restaurant', 'fast food', 'pubs', etc to the 'Eating Out' target, for easier readability.) as well as to control colors for flows/nodes.

## Tags
Tags can be used to configure the diagram in a couple of different ways:

### Basic tag usage
- Tags can be used to create a new end node with the tag name(s).
  - Example usage (using sample datasets): `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --all_time --tags "Ford, Dodge"`
- Tags can override the normal assignment of sources and targets using the 'tag' type entries in the labels spreadsheet.
  - Example usage (using sample datasets): `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --all_time --tags "Ford, Dodge" --tag_override`
  - Note: In tag_override mode, if an entry in labels spreadsheet is not found for the supplied tag, a new flow will be created "Income -> <tag name>"

Notes:
- If multiple tags are specified and a given transaction matches more than one, only the first tag matched will be used.
- Combining 'tags' and 'stores' filtering is not supported.

### Excluding transactions with tags
Tags can also be used if you want to exclude certain transactions from the visualization.
- This is done prior to any other processing.
- Example usage (using sample datasets): `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --all_time --exclude "Onetime"`

### Using source tags ('s-tags')
Unlike other tag types which modify cash flows downstream from "Income" node, s-tags create a new sink that functions like Income, except with the tag name(s).
- Example usage (using sample datasets): `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --all_time --tags "Joe"`

## Stores
Cash flow to a specified store or stores (whatever is in the 'Description' column) can be visualized as end nodes.
- Note: string matches must be exact.
- Example usage (using sample datasets): `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --all_time --stores "Trader Joe's, McDonald's"`

## Range
A time range can be specified for filtering with `-r`/`--range`, which will prompt you to enter start/end dates. Pass `--all_time` instead to skip the prompt and include every transaction.

## Miscellaneous
- Distributions
	- If used, transactions with a value in the 'Distributions' column will be equally apportioned over the number of months specified, starting with the date of the transaction. Eg, if I had a $120 transaction with a distributions value of 12, then the transaction amount would be changed to $10 and 11 additional synthetic transactions would be created over the subsequent 11 months of $10 each. In this mode, sales tax amounts will also be distributed.
- All-time
	- By default, the visualization will bound by the start date in `AppSettings.DEFAULT_START_DATE` and the current date (in case you have pre-entered some data or are using distributions). This can be overridden either by supplying a specific date range using 'range' or by passing in the 'all_time' flag, which will force all past and future transactions to be handled.
- Separate tax
	- If used, sales tax will be combined into a single aggregate flow from Income instead of branching from terminal nodes.
	- Example usage (using sample datasets): `sankeyd -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --all_time --separate_tax`
- DEDUCTIONS
	- This is not a param, but instead is a source you can specify on a label, if set it will dynamically update the source for any transactions which match that label to instead use the value in "Description" for the transaction.
	- Example: in the sample data you have the following transactions:
		| 1/1/21 | Joe Job | Boeing | .. | $4,000.00 |
		| 1/1/21 | Income Tax | Joe Job | .. | $700.00 |
		| 1/1/21 | Health Insurance | Joe Job | .. | $100.00 |
	  The first line will map to "Joe Job" -> "Income" as expected, but the next two lines have a source of "DEDUCTIONS" in the sources-targets sheet, and will therefore be updated to "Joe Job" -> "Income Tax" and "Joe Job" -> "Health Insurance", bypassing the Income node entirely.
- Line charts (`--dtype line`)
	- An alternative to the Sankey diagram: a line chart of spend over time, grouped by each label's Classification column. You'll be prompted for a chart resolution (day, week, or month). Less mature than the Sankey diagram - can get noisy for large datasets, and 'Income', 'Uncategorized', and any Classification prefixed with 'x' are hidden by default.
- Audit mode (`--audit`)
	- Compares your transaction data against a bank export CSV (Date, Amount, Description columns) to flag transactions that may be missing from your data, rather than generating a diagram.
