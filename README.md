# Sankey diagram generator

## Information
Create configurable sankey visualizations of cashflow based on transaction data.

## Setup
- `git clone git@github.com:paulkm/projects.git`
- `python3 -m venv venv`
- `source venv/bin/activate`
- `pip3 install -r requirements.txt`
- `chmod +x sankeyd.py`
- Create a service account using the instructions here: https://pygsheets.readthedocs.io/en/stable/authorization.html and copy the downloaded crendentials.json file to the project directory as 'google_service_account_key.json' or by calling sankeyd using the `--cred` arg pointing to the location of your credentials file.

## Running
- `./sankeyd.py --help`
- `./sankeyd.py -s <name of a Google Sheets document> -t <worksheet name for transactions> --srcmap <worksheet name for sources-targets> --creds <location of service account credentials file>`
	- `-t`, `--srcmap`, and `--creds` are all optional and if omitted will default to 'current_exp', 'Sources-Targets', and './google_service_account_key.json' respectively. 
- `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv'`

## Data prerequisites
Two sheets are needed, either in a Google Sheets workbook or as two CSV files.

### Transactions
The following columns, in this order, are required:
- Date
	- Required. Date formatted string, eg. 'MM/DD/YYYY'
- Category
	- Required. Must match with category in sources-targets sheet in order to be correctly categorized.
- Description
	- Required. Free text but should be consistent for the `--store` param to work as expected.
- Tags
	- Optional. Comma-delimited strings.
- Comments
	- Optional. Free text.
- Source
	- Optional. If specified, will override default categorization. If set, Target must also be set.
- Target
	- Optional. If specified, will override default categorization. Note, if Target set but not source, will append to normal categorization.
- Type
	- Not used here.
- Distribution
	- Optional. Integer value of months to divide transaction into.
- Amount
	- Required. Dollar amount of transaction (minus sales tax/tip if being used). Will accept $x,xxxx.xx or x,xxx.xx or xxxx.xx.
- Sales Tax
	- Optional. Dollar amount of transaction sales tax. Will accept $x,xxxx.xx or x,xxx.xx or xxxx.xx.
- Tips
	- Optional. Dollar amount of tip. Will accept $x,xxxx.xx or x,xxx.xx or xxxx.xx.

### Labels (sources-targets)
The following columns, in this order, are required:
- Category Name
	- Required. Name to match transactions with. Case sensitive.
- Type
	- Optional. Allowed values:
		- computed. Indicates a 'intermediate' node for longer flows, eg "Income" -> "Household".
		- tag. Indicates a label that would only be used during tag overrides. Ignored for normal lookups.
		- s-tag. Indicates a special "Source tag". See notes on tag handling below for usage.
- Source
	- Optional. Source node for any transaction matching this category. If not specified, label will only be used for color lookups.
- Target
	- Optional. Source node for any transaction matching this category. If not specified, label will only be used for color lookups.
- Link color
	- Optional. RGB+Alpha value as string, eg: 'rgba(179, 204, 230, 0.8)'
- Node color
	- Optional. RGB+Alpha value as string, eg: 'rgba(179, 204, 230, 1.0)'
- Comments
	- Optional. Free text.		


## Usage notes
- All data rows are positive values with the labels sheet controlling whether they flow into or out of the "Income" node. (all income types flow in, all expenses flow out).
- The labels sheet is used to map particular categories to a source-target pair (eg, you might combine anything categorized as 'restaurant', 'fast food', 'pubs', etc to the 'Eating Out' target, for easier readability.) as well as to control colors for flows/nodes.

## Tags
Tags can be used to configure the diagram in a couple of different ways:

### Basic tag usage
Create a new terminal node with the tag name(s):
- Example usage (using sample datasets): `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --tags "Ford, Dodge"`

Override the normal assignment of sources and targets using the 'tag' type entries in the labels spreadsheet.
- Example usage (using sample datasets): `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --tags "Ford, Dodge" --tag_override`
- Note: In tag_override mode, if an entry in labels spreadsheet is not found for the supplied tag, a new flow will be created "Income -> <tag name>"

Notes:
- If multiple tags are specified and a given transaction matches more than one, only the first tag matched will be used.
- Combining 'tags' and 'stores' filtering is not supported.

### Excluding transactions with tags
Used if you want to exclude certain transactions from the visualization.
- Example usage (using sample datasets): `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --exclude "Onetime"`
- This is done prior to any other processing.

### Using source tags ('s-tags')
Unlike other tag types which modify cash flows downstream from "Income" node, s-tags create a new sink that functions like Income, except with the tag name(s).
- Example usage (using sample datasets): `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --tags "Joe"`

## Stores
Cash flow to a specified store or stores can be visualized using the 'stores' param.
- Example usage (using sample datasets): `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --stores "Trader Joe's, McDonald's"`
- Note: Matches must be exact.

## Range
A time range can be specified for filtering.
- Example usage (using sample datasets): `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --range`
- It will prompt you to enter start/end dates.

## Miscellaneous
- `--distributions`
	- If enabled, transactions with a value in the 'Distributions' column will be equally apportioned over the number of months specifed, starting with the date of the transaction. Eg, if I had a $120 transaction with a distributions value of 12, then the transaction amount would be changed to $10 and 11 additional synthetic transactions would be created over the subsequent 11 months of $10 each. In this mode, sales tax amounts will also be distributed.
- `--include_future`
	- By default, the day you run the visualization will be the end date for processing (in case you have pre-entered some data or are using distributions). This can be overridden either by supplying a specific date range using 'range' or by passing in the 'include_future' flag, which will force all future transactions to be handled.
- `--separate_tax`
	- If enabled, sales tax will be combined into a single aggregate flow from Income instead of branching from terminal nodes.
	- Example usage (using sample datasets): `./sankeyd.py -s 'sample_data/expenses.csv' --srcmap 'sample_data/labels.csv' --separate_tax`
- `DEDUCTIONS`
	- This is not a param, but instead is a source you can specify on a label, if set it will dynamically update the source for any transactions which match that label to instead use the value in "Description" for the transaction.
	- Example: in the sample data you have the following transactions:
		| 1/1/21 | Joe Job | Boeing | .. | $4,000.00 |
		| 1/1/21 | Income Tax | Joe Job | .. | $700.00 |
		| 1/1/21 | Health Insurance | Joe Job | .. | $100.00 |
	  The first line will map to "Joe Job" -> "Income" as expected, but the next two lines have a source of "DEDUCTIONS" in the sources-targets sheet, and will therefore be updated to "Joe Job" -> "Income Tax" and "Joe Job" -> "Health Insurance", bypassing the Income node entirely.


