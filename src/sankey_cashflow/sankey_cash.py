import pygsheets
import pandas as pd
import plotly.graph_objects as go
import argparse
import datetime
from os import path
from numpy import isnan, float64
from csv import DictReader
import re
import networkx as nx
from uuid import uuid4
# Types
from pandas._libs.tslibs import timestamps, nattype

# import pdb

# See: https://lifewithdata.com/2022/08/29/how-to-create-a-sankey-diagram-in-plotly-python/
# https://erikrood.com/Posts/py_gsheets.html
# https://github.com/nithinmurali/pygsheets
# https://pygsheets.readthedocs.io/en/stable/
# More complex example: https://plotly.com/python/sankey-diagram/


# Notes:
#  - About mutability: Pandas DataFrames are mutable except when they're not... I am treating them as immutable here and when necessary to make changes using return values and re-assignment. From the Pandas docs:
#     ## Mutability and copying of data
#       All pandas data structures are value-mutable (the values they contain can be altered) but not always size-mutable. The length of a Series cannot be changed, but, for example, columns can be inserted into a DataFrame.
#       However, the vast majority of methods produce new objects and leave the input data untouched. In general we like to favor immutability where sensible.
# - Permissions: Create a service account and download credentials in json format, (detailed instructions here: https://pygsheets.readthedocs.io/en/stable/authorization.html)
#                then share spreadsheet to service account user
# - Tag usage scenarios:
#   - Override sources/targets on individual tag level using --tags arg. [done]
#   - Explode all tags...
# TODO: make tag/store overrides as source with previous category assignments preserved [done, except as targets]
# TODO: prevent multiple s-tags

# Define some classes =================================================================================================


class AppSettings:
    """
      Application settings and defaults + validation, getters/setters, etc
    """
    def __init__(self, args):
        self.DEFAULT_START_DATE = pd.to_datetime("10/1/2022")
        self.data_source = args.source
        self.data_sheet = args.sheet or "current_exp"
        self._labels_source = args.srcmap or "Sources-Targets"
        self.filter_dates = args.range
        self.separate_taxes = args.separate_tax
        self.verbose = args.verbose
        self._g_creds = args.creds or './google_service_account_key.json'
        self.distribute_amounts = args.distributions
        self.all_time = args.all_time
        self.recurring = args.recurring
        self.base_title = "Cashflow"
        self._date_filter_start = None
        self._date_filter_end = None
        self.tags = None
        self.feed_in = None
        self.exclude_tags = None
        self.stores = None
        self.tag_override = False
        if args.tags:
            self.tags = [i.strip() for i in args.tags.split(',')]
            if args.tag_override:
                self.tag_override = True
            if args.feed_in:
                self.feed_in = True
        if args.exclude:
            self.exclude_tags = [i.strip() for i in args.exclude.split(',')]
        if args.stores:
            self.stores = [i.strip() for i in args.stores.split(',')]
        self.colors = {}  # label: [link, node]
        if self.tags and self.stores:
            raise Exception("Stores and tags visualizations should not be combined!")
        self.validate_sources()

    @property
    def date_filter_start(self):
        return self._date_filter_start

    @date_filter_start.setter
    def date_filter_start(self, val):
        if not val or len(val) == 0:
            self._date_filter_start = None
        else:
            self._date_filter_start = pd.to_datetime(val)

    @property
    def date_filter_end(self):
        return self._date_filter_end

    @date_filter_end.setter
    def date_filter_end(self, val):
        if not val or len(val) == 0:
            self._date_filter_end = None
        else:
            self._date_filter_end = pd.to_datetime(val)

    @property
    def g_creds(self):
        return self._g_creds

    @g_creds.setter
    def g_creds(self, val):
        if not val or len(val) == 0 or not path.isfile(val):
            raise Exception(f"Credentials file not found: {val}")
        self._g_creds = val

    @property
    def labels_source(self):
        return self._labels_source

    @labels_source.setter
    def labels_source(self, val):
        if not val or len(val) == 0 or not path.isfile(val):
            raise Exception(f"Sources-targets file not found: {val}")
        self._labels_source = val

    def source_data_location(self):
        if self.data_source.endswith('.csv'):
            return self.data_source
        else:
            return f"{self.data_source}: {self.data_sheet}"

    def validate_sources(self):
        # check sources etc
        if not self.data_source or len(self.data_source) == 0:
            print("Please enter a valid data source!")
            raise Exception("Missing data source.")

        if self.data_source.endswith(".csv"):
            # Using csv data source
            # Note: additional data validation happens when loading this data
            if not self.labels_source or not self.labels_source.endswith(".csv"):
                raise Exception("A csv sources-targets sheet must be used when using csv source data.")
            if not path.isfile(self.data_source):
                raise Exception(f"Could not find provided data source: {self.data_source}")
            if not path.isfile(self.labels_source):
                raise Exception(f"Could not find provided sources-targets source: {self.labels_source}")
        else:
            # Using Google Sheets data source
            # Note: additional access/permissions/data validation happens when fetching and loading this data
            if not self.data_sheet or len(self.data_sheet) == 0:
                raise Exception("Missing Google worksheet name.")
            if not self.labels_source or len(self.labels_source) == 0:
                raise Exception("A sources-targets sheet name must be supplied.")
            if not self.g_creds or len(self.g_creds) == 0:
                raise Exception("Google service account credentials must be provided.")
            if not path.isfile(self.g_creds):
                raise Exception(f"Invalid service account credential file provided: {self.g_creds}")


class RowLabels:
    """
      Contains row label data and methods, used to map data categories to source, target, and color information. Accepts an array of dicts on init which can come from a Google sheet or csv.
      Data looks like: [{'Category Name': 'House', 'Type': 'computed', 'Source': 'Income', 'Target': 'House', 'Link color': 'rgba(153, 187, 255, 0.8)', 'Node color': 'rgba(102, 153, 255, 1)', 'Comments': '', '': ''}]
      Also creates a DAG with source target edges based on labels definitions
    """
    def __init__(self, labeldata):
        self._labeldata = labeldata
        self._digraph = nx.DiGraph()
        self._digraph.add_node("Income", ntype="income")
        self.process_report = f"RowLabel report\n{'='*60}\n\n\n"
        required_columns = ['Category Name', 'Type', 'Source', 'Target', 'Link color', 'Node color']
        if False in [k in self._labeldata[0].keys() for k in required_columns]:
            raise Exception(f"Sources-Targets sheet does not have all required columns! Needed: {required_columns}. Found: {list(self._labeldata[0].keys())}")
        self._available_attributes = ['source', 'target', 'link_color', 'node_color', 'type']
        # TODO: validation
        self._lookup = {}
        # Map out data to lookup dict
        for i in self._labeldata:
            if len(i['Category Name']) == 0:  # Skip empties
                self.process_report += f"SKIPPING: {i}\n"
                continue
            if i['Category Name'] in self._lookup:
                raise Exception(f"Duplicate label! {i['Category Name']}")
            # Add to internal lookup dict
            self.process_report += f"ADDING LOOKUP: {i}\n"
            self._lookup[i['Category Name']] = {'source': i.get('Source'), 'target': i.get('Target'), 'link_color': i.get('Link color'), 'node_color': i.get('Node color'), 'type': i.get('Type')}
            if i.get("Source") == "DEDUCTIONS":
                # These have to be dynamically generated - skip adding to DAG for now (or maybe entirely)
                # TODO (maybe): switch to using type and/or DAG attributes
                self.process_report += f"SKIPPING DEDUCTION: {i}\n"
                continue
            if i["Type"] in ['tag', 's-tag']:
                # NOT adding tag labels to graph - if needed they will be added on the fly
                # TODO: investigate using DAG attributes instead. Test with distant/complex tag targets.
                if i["Type"] == 's-tag':
                    self.process_report += f"Adding NODE for s-tag: {i} to DAG\n"
                    self._digraph.add_node(i['Category Name'], type='s-tag')
                else:
                    self.process_report += f"NOT Adding tag: {i} to DAG\n"
                continue
            if i.get('Source') and i.get('Target'):  # Add all source/target pairs as edges to DAG
                # Add to DAG
                if i.get('Type'):
                    self.process_report += f"ADDING EDGE: {i.get('Source')} -> {i.get('Target')} (ntype={i.get('Type')})\n"
                    self._digraph.add_edge(i.get('Source'), i.get('Target'), ntype=i.get('Type'))
                else:
                    self.process_report += f"ADDING EDGE: {i.get('Source')} -> {i.get('Target')}\n"
                    self._digraph.add_edge(i.get('Source'), i.get('Target'))
            else:
                self.process_report += f"ERROR (SKIPPING): {i}\n"
                print(f"Category: {i['Category Name']} yielded an empty source and/or target! {i.get('Source')}:{i.get('Target')}")

    @property
    def data(self):
        return self._labeldata

    def get_longest_path(self):
        return nx.dag_longest_path(self._digraph)

    def get_path(self, source, target):
        path = [i for i in nx.all_simple_paths(self._digraph, source, target)]
        # Note path obj may contain 0 or multiple paths
        if not path or len(path) == 0:
            print(f"No path found for {source}:{target}")
        elif len(path) > 0:
            print(f"Multiple paths found for {source}:{target}. ({path})")
        else:
            return path[0]

    def get_label(self, labelname, labeltype=None):
        """
          Return a label name & tag pair or None
        """
        item = self._lookup.get(labelname)  # TODO: test duplicate category names
        if labeltype == "any":
            return item
        if labeltype and labeltype == "tag":
            if item and item.get('type') == 'tag':
                return item
            return None
        elif labeltype and labeltype == "s-tag":
            if item and item.get('type') == 's-tag':
                return item
            return None
        if item and item.get('type') not in ['tag', 's-tag']:
            return item
        return None

    def get_attribute(self, labelname, labelattribute, use_default=True, labeltype=None, original_category=None):
        """
          Get named attribute by label. Cases:
            Unknown attribute: raise exception
            label & labeltype are exist:
              attribute exists: return attribute
              attribute doesn't exist: return default attribute
            label & labeltype doesn't exists:
              return default attributes
        """
        if labelattribute not in self._available_attributes:
            raise Exception(f"Unknown attribute: {labelattribute}")
        if labelattribute == "type":
            item = self.get_label(labelname, "any")
        else:
            item = self.get_label(labelname, labeltype)
        default_item = self.get_label('default')
        if item:
            if labelattribute == "type":
                return item.get("type", "")
            if not is_null(item[labelattribute]) and len(item[labelattribute]) != 0:
                return item[labelattribute]
        elif labelattribute == "type":
            return None
        if use_default:
            # Did not find the attribute - use defaults
            if labelattribute == "source":
                return "Uncategorized"
            if labelattribute == "target":
                return labelname
            if labelattribute in ["node_color", "link_color"]:
                return default_item[labelattribute]
        return None

    def print_graph(self, filename):
        from matplotlib import pyplot as plt
        plt.tight_layout()
        nx.draw_networkx(self._digraph, arrows=True)
        # plt.figure(figsize=(20,20))
        plt.savefig(filename,dpi=200,format="PNG")
        plt.clf()


class Transactions:
    """
      Contains transaction data and all helper methods for transforming and outputing.
      init with a Pandas dataframe from Google Sheets or a csv. NOTE: depending on the activity, dataframes are mutable.
      TODO:
        empty values from CSV are 'NaN'
        Make sure various synthetic entries don't cause problems for other computations
        Make sure that various methods can be run in any order, or enforce precedence/locking
    """
    def __init__(self, dataframe, labels_obj, app_settings_obj):
        self._df = dataframe
        self._grouped_df = None
        self.length = len(dataframe)
        self._app_settings = app_settings_obj
        self._labels_obj = labels_obj
        is_valid = self._validate_df()
        if not is_valid[0]:
            raise Exception(f"Source columns failed validation! Error was: {is_valid[1]}")
        # Convert all dates to datetimes and sort earliest to latest
        if self._app_settings.verbose:
            print(f"Converting data in {self.length} fetched rows to datetimes...")
        self._df["Date"] = pd.to_datetime(self._df["Date"]) # Does not mutate dataframe
        if nattype.NaTType in [type(i) for i in self._df["Date"]]:
            raise Exception("Empty date found!")  # There is probably a better way to do this.
        self.earliest_date = self._df["Date"].sort_values().iloc[0]  # Returns pandas._libs.tslibs.timestamps.Timestamp
        self.latest_date = self._df["Date"].sort_values().iloc[len(self._df)-1]
        self.default_date = self.latest_date - datetime.timedelta(days=1)
        self.max_depth = 1
        self.tips_processed = False
        self.sales_tax_processed = False
        self.surplus_deficit_processed = False
        self.amount_distributions = False
        self.process_report = f"Transactions report\n{'='*60}\n\n\n"

    def _validate_df(self):
        # Validate header row
        return DataRow.validate(self._df.columns.to_list(), True)

    def process(self, date_range=None):
        """
          Step 1: Drop rows based on tag exclusions
          Step 2: Split out any entries containing distributions (if feature flag is turned on)
          Step 3: Apply date filtering (if applicable)
          Step 4: Update transaction rows with sources and targets as defined by labels spreadsheet for all entries, modify sources/targets based on tags & store filters. Also handle recurring items.
          Step 5: Loop through each entry and:
               a: check for sales tax and/or tips column. Update total amount and create synthetic flows for tax/tips.
               b: crawl back through DAG, creating synthetic entries for predecessor nodes along the way, to ensure flows appear correctly.
          Step 6: Compute surplus or deficit flows
          Step 7: aggregate amounts for all shared source:target pairs
        """

        dt_today = datetime.datetime.today()
        self.process_report += f"Processing {len(self._df)} transactions from {self._app_settings.source_data_location()}\n{'-'*60}\n"
        if self._app_settings.verbose:
            print(f"Processing {len(self._df)} transactions from {self._app_settings.source_data_location()}")

        # Step 1:
        if self._app_settings.exclude_tags:
            self.process_report += f"Checking for tags to exclude: {self._app_settings.exclude_tags}\n{'-'*60}\n"
            df_changed = False
            rows_to_drop = []
            for k,v in enumerate(self._df["Tags"]):
                tag_matches = DataRow.tag_matches(v, self._app_settings.exclude_tags)  # None if either arg is None or if no matches
                if tag_matches:
                    df_changed = True
                    rows_to_drop.append(self._df.index[k])
            if df_changed and rows_to_drop:  # Do as a separate loop to avoid changing the frame as we're iterating over it.
                for row_idx in rows_to_drop:
                    self.process_report += f"DROPPING row due to exclude tags: {self._df.loc[row_idx]}\n"
                    if self._app_settings.verbose:
                        print(f"DROPPING row due to exclude tags: {self._df.loc[row_idx]}")
                    self._df.drop(row_idx, inplace=True)
            if df_changed:
                self._df.reset_index(inplace=True, drop=True)

        # Step 2:
        if self._app_settings.distribute_amounts:
            if self._app_settings.verbose:
                print("Distributing amounts...")
            self.distribute_amounts()  # process report logging happens in called method

        # Step 3:
        if self._app_settings.filter_dates:
            if not date_range:
                raise Exception("Filter dates flag was True, but no dates were passed in!")
            start_date = date_range[0]
            end_date = date_range[1]
            if end_date is None and not self._app_settings.all_time:
                end_date = dt_today
            if start_date is None and not self._app_settings.all_time:
                start_date = self._app_settings.DEFAULT_START_DATE
            self.process_report += f"Filtering for dates from {start_date} to {end_date}\n{'-'*60}\n"
            if self._app_settings.verbose:
                print(f"Filtering for dates from {start_date} to {end_date}")
            # TODO: test and find edge cases!
            self.filter_dates(start_date, end_date)
        elif not self._app_settings.all_time:
            self.filter_dates(self._app_settings.DEFAULT_START_DATE, dt_today)

        self.update_title()
        # Step 4:
        self.apply_labels()
        # Step 5:
        self.process_rows()
        # Step 6:
        self.create_surplus_deficit_flows()
        # Step 7:
        self.collapse()
        # -- END Transactions.process() --

    def add_row(self, row_data, already_validated=False):
        idx = len(self._df)  # Could use self.length...
        if already_validated:
            self._df.loc[idx] = row_data
        else:
            self._df.loc[idx] = DataRow.validate(row_data)
        self.length = idx + 1

    def apply_labels(self):
        """
          Loop through each row in dataframe, looking up source-target nodes using category names, and overriding if indicated by tags or stores flags.
          Also add each source:target pair as an edge in a DAG.
          NOTE: this process will not be adding intermediate transactions, but will ensure the DAG is correct so that intermediate transactions can be added later.
        """
        self.process_report += f"Running Transactions.apply_labels(). Tags has: {self._app_settings.tags}, tag_override is {self._app_settings.tag_override} and stores has: {self._app_settings.stores}\n\n"
        if self._app_settings.tags and self._app_settings.verbose:
            print(f"Tag search enabled: Looking for tags: {self._app_settings.tags}")
            if self._app_settings.tag_override:
                print("Overriding tags...")
        if self._app_settings.stores and self._app_settings.verbose:
            print(f"Store search enabled: Looking for stores: {self._app_settings.stores}")
        if self._app_settings.verbose:
            print(f"Applying labels for {len(self._df)} transactions")

        if self._app_settings.recurring:
            if self._app_settings.verbose:
                print("Recurring transactions to be split out")  # TODO: precludes tag:recurring handling.
            # Add edge from Income to Recurring
            self._labels_obj._digraph.add_edge("Income", "Recurring")

        # Util functions ...................................................................................
        def get_source_target_labels(this_obj, this_category_key, this_category_val, step_id):
            # Get default labels defined for category from sources-targets sheet, override from data sheet if set there.
            src = this_obj._labels_obj.get_attribute(this_category_val, "source")
            tgt = this_obj._labels_obj.get_attribute(this_category_val, "target")
            this_obj.process_report += f"[{step_id}] Found default src:target for {this_category_val} -> {src}:{tgt}\n"
            # Allow individual transaction rows to override label lookups
            data_override_s_t = False
            transaction_source = this_obj._df.at[this_category_key, "Source"]
            transaction_target = this_obj._df.at[this_category_key, "Target"]
            if not is_empty(transaction_source) and not is_empty(transaction_target):
                # Both a source and target were specifed in the transaction data
                src = transaction_source
                tgt = transaction_target
                data_override_s_t = True
            elif not is_empty(transaction_source) and is_empty(transaction_target):
                # A source but not target were specifed in the transaction data
                src = transaction_source
                data_override_s_t = True
            elif is_empty(transaction_source) and not is_empty(transaction_target):
                # A Target but not source were specifed in the transaction data, we will append it to the default source-target
                if transaction_target != tgt:  # Skip if the override is the same as the default target
                    if not this_obj._labels_obj._digraph.has_edge(src, tgt):
                        this_obj._labels_obj._digraph.add_edge(src, tgt)
                    src = tgt
                    tgt = transaction_target
                    data_override_s_t = True

            if data_override_s_t:
                this_obj.process_report += f"[{this_step_id}] Override source/target for {this_category_val} from transaction data -> {src}:{tgt}\n"

            return src,tgt

        # MAIN LOOP ........................................................................................

        for k,v in enumerate(self._df["Category"]):
            # Main labeling loop. Iterate over each transaction, look up source-target information in labels spreadsheet applying/overriding as indicated.
            this_step_id = str(uuid4())[:8]
            self.process_report += f"[{this_step_id}] START Processing {self._df.at[k, 'Date']} | {v} | {self._df.at[k, 'Tags']} | ${self._df.at[k, 'Amount']}\n"
            is_deduction = False
            if is_empty(v):
                # Note: this should not happen... raise exception instead?
                self.process_report += f"[{this_step_id}] SKIPPING empty category {self._df.loc[k]}\n"
                print(f"Skipping empty category {self._df.loc[k]}")
                continue
            # Tag logic
            # TODO: test source tags

            this_source, this_target = get_source_target_labels(self, k, v, this_step_id)

            # Handle deduction types (these go directly from a income to an expense, skipping the 'Income' category and have a variable source based on their description)
            # Use case is a transaction with income would normally be something like "My Job" -> "Income" and then a second transaction with income taxes would be "My Job" -> "Income Taxes" (skipping income category)
            # TODO: Verify this works correctly with s-tags
            if this_source == "DEDUCTIONS":
                this_source = self._df.at[k, "Description"]
                self._df.at[k, "Type"] = "deduction"
                is_deduction = True
                self.process_report += f"[{this_step_id}] Deduction type found src:target -> {this_source}:{this_target}\n"
                if self._app_settings.verbose:
                    print(f"Found DEDUCTION type transaction. Set to {this_source}:{this_target}")

            if self._app_settings.recurring and this_source == "Income":
                # Replace with recurring
                this_source = "Recurring"
            # Verify base edge is in DAG
            if not self._labels_obj._digraph.has_edge(this_source, this_target):
                print(f"Edge: {this_source}:{this_target} not found! Adding to graph.")
                self._labels_obj._digraph.add_edge(this_source, this_target)

            if not is_deduction:  # For now logic around tags/stores with deductions flow is undefined - skip processing.
                # Check for store match
                store_matches = False
                if self._app_settings.stores:
                    this_name = self._df.at[k, "Description"]
                    if self._app_settings.stores and this_name in self._app_settings.stores:
                        store_matches = True

                # Check for tag match(es)
                # Note currently we will only ever use the first match.
                tag_matches = DataRow.tag_matches(self._df.at[k, "Tags"], self._app_settings.tags)  # None if flag is not enabled or no matches
                tag_type = None
                if tag_matches:
                    if self._app_settings.recurring and tag_matches and tag_matches[0] == "Recurring":
                        raise Exception("Not double processing recurring tags!")  # TODO: handle more quietly
                    if self._app_settings.verbose:
                        print(f"Got tag matches: {tag_matches}")
                    # Check for s-tags
                    # Get tag type
                    tag_type = self._labels_obj.get_attribute(tag_matches[0], "type")
                    if tag_type == "s-tag":
                        # If the flow is directly to/from "Income", replace "Income" with the Tag
                        if this_source == "Income":
                            this_source = tag_matches[0]
                        elif this_target == "Income":
                            this_target = tag_matches[0]
                        else:
                            self._labels_obj._digraph.add_edge(this_source, this_target, type="s-tag")
                            # NOTE: if tag is distant from "Income", we'll need to handle it while reconciling DAG
                    elif self._app_settings.tag_override:
                        # If overriding tags, we'll use the labels sheet to determine placement
                        this_source = self._labels_obj.get_attribute(tag_matches[0], "source", labeltype="tag", use_default=False)
                        this_target = self._labels_obj.get_attribute(tag_matches[0], "target", labeltype="tag", use_default=False)
                        if not this_source:
                            # If we don't have matching tag defined in sources-targets sheet, just create it to/from income
                            def_target = self._labels_obj.get_attribute(v, "target", use_default=False)  # lookup the target we would have without tag matching
                            if def_target == "Income":  # Note: Breaks if we have income flows more than one deep
                                this_source = tag_matches[0]
                                this_target = "Income"
                            else:
                                this_source = "Income"
                                this_target = tag_matches[0]
                    else:
                        # We are appending the tags as new target to the end of the flow
                        this_source = this_target
                        this_target = tag_matches[0]
                        if self._app_settings.verbose:
                            print(f"Adding edge to graph for tag ({tag_matches}[0]): {this_source} -> {this_target}")
                        # self._labels_obj._digraph.add_edge(this_source, this_target)

                if store_matches:
                    this_source = this_target
                    this_target = self._df.at[k, "Description"]
                    if self._app_settings.verbose:
                        print(f"Adding edge to graph for store ({this_name}): {this_source} -> {this_target}")
                    # self._labels_obj._digraph.add_edge(this_source, this_target)

            self.process_report += f"[{this_step_id}] RESOLVED src:target for {v} -> {this_source}:{this_target}\n"
            if self._app_settings.verbose:
                print(f"RESOLVED source/target > {this_source}:{this_target}")
            # Circuit breaker
            if is_empty(this_source) or is_empty(this_target):
                raise Exception(f"Got empty source or target for category {v}! ({this_source}:{this_target})")

            # Check for final edge in DAG and add if necessary
            if not self._labels_obj._digraph.has_edge(this_source, this_target):
                print(f"Edge: {this_source}:{this_target} not found! Adding to graph.")
                self._labels_obj._digraph.add_edge(this_source, this_target)

            # Sanity check that we haven't created an orphan edge
            if not (is_deduction or tag_type == 's-tag') and "Income" not in nx.ancestors(self._labels_obj._digraph, this_target) and "Income" not in nx.descendants(self._labels_obj._digraph, this_source):
                print(f"{self._df.loc[k]}")
                raise Exception(f"No path to \'Income\' from {this_source}:{this_target}")

            # Set source-target on original transaction
            self._df.at[k, "Source"] = this_source
            self._df.at[k, "Target"] = this_target

            self.process_report += f"[{this_step_id}] FINISHED processing labels\n"


    def process_rows(self):
        """
          Process individual transactions, creating synthetic transactions as needed to satisfy flows
        """
        msg = f"Processing row data on {len(self._df)} rows"
        self.process_report += f"\n{'-'*60}\nRunning Transactions.process_rows()\n{'-'*60}\n"
        self.process_report += msg + "\n"
        if self._app_settings.verbose:
            print(msg)
        for k,v in enumerate(self._df["Source"]):
            this_row = self._df.loc[k]
            this_step_id = str(uuid4())[:8]
            is_recurring = False
            self.process_report += f"[{this_step_id}] START Processing {self._df.at[k, 'Date']} | {self._df.at[k, 'Description']} | ${self._df.at[k, 'Amount']}\n"
            if self._app_settings.verbose:
                print(f"{'-'*40}\nGot a transaction: {self._df.at[k, 'Date']} | {self._df.at[k, 'Description']} | {self._df.at[k, 'Source']}:{self._df.at[k, 'Target']} | ${self._df.at[k, 'Amount']}\n")

            # Check for tag match(es)
            # Note currently we will only ever use the first match.
            # TODO: discard tag if tag is "Recurring" AND _app_settings.recurring is True
            tag_matches = DataRow.tag_matches(self._df.at[k, "Tags"], self._app_settings.tags)  # None if flag is not enabled or no matches
            tag_type = None
            if tag_matches:
                tag_type = self._labels_obj.get_attribute(tag_matches[0], "type")  # Get tag type

            # Check for recurring tag
            has_recurring = DataRow.tag_matches(self._df.at[k, "Tags"], ["Recurring"])
            if self._app_settings.recurring and has_recurring and "Recurring" in has_recurring:
                is_recurring = True
            if self._app_settings.verbose:
                print(">> Processing recurring transaction")

            # Handle taxes
            if not is_empty(this_row["Sales Tax"], True):
                if self._app_settings.separate_taxes:
                    # Add sales tax to it's own root category as a new row
                    self.process_report += f"[{this_step_id}] ADDED: {this_row.Date} | {this_row.Description} | 'Income' -> 'Sales Tax' | ${this_row['Sales Tax']}\n"
                    self.add_row(DataRow.create(
                        date=this_row.Date,
                        category_name="Sales Tax",
                        amount=this_row["Sales Tax"],
                        source="Income",
                        target="Sales Tax",
                        description=this_row.Description,
                        tags=this_row.Tags,
                        comment='Synthetic row for sales tax',
                        distribution=this_row.Distribution
                    ), True)
                else:
                    # Create new sales tax child target from this original target row & add sales tax back to original row amount
                    # Note: if store or tag processing is being done, this may already be one removed from the original category
                    self.process_report += f"[{this_step_id}] ADDED: {this_row.Date} | {this_row.Description} | {this_row.Target} -> 'Sales Tax' | ${this_row['Sales Tax']}\n"
                    if not is_empty(this_row["Sales Tax"], True):
                        self.add_row(DataRow.create(
                            date=this_row.Date,
                            category_name="Sales Tax",
                            amount=this_row["Sales Tax"],
                            source=this_row.Target,
                            target="Sales Tax",
                            description=this_row.Description,
                            tags=this_row.Tags,
                            comment='Synthetic row for sales tax',
                            distribution=this_row.Distribution
                        ), True)
                        self._df.at[k, "Amount"] = round(this_row.Amount + this_row["Sales Tax"], 2)  # For this to behave as expected, it needs to add the sales tax amount back to the original Amount
                        self.process_report += f"[{this_step_id}] UPDATED: {this_row.Date} | {this_row.Description} | {this_row.Source} -> {this_row.Target} | ${this_row.Amount} -> ${self._df.at[k, 'Amount']}\n"


            # Handle tips by creating new Tips child target from this original target row & add tip back to original row amount
            # Note: if store or tag processing is being done, this may already be one removed from the original category
            if not is_empty(this_row["Tips"], True):
                self.process_report += f"[{this_step_id}] ADDED: {this_row.Date} | {this_row.Description} | {this_row.Target} -> 'Tips' | ${this_row['Tips']}\n"
                orig_amount = self._df.at[k, "Amount"]  # Sales tax computation may have changed from this_row.Amount value
                self.add_row(DataRow.create(
                    date=this_row.Date,
                    category_name="Tips",
                    amount=this_row["Tips"],
                    source=this_row.Target,
                    target="Tips",
                    description=this_row.Description,
                    tags=this_row.Tags,
                    comment='Synthetic row for tips',
                    distribution=this_row.Distribution
                ), True)
                self._df.at[k, "Amount"] = round(orig_amount + this_row["Tips"], 2)  # For this to behave as expected, it needs to add the tips amount back to the original Amount
                self.process_report += f"[{this_step_id}] UPDATED: {this_row.Date} | {this_row.Description} | {this_row.Source} -> {this_row.Target} | ${orig_amount} -> ${self._df.at[k, 'Amount']}\n"

            # Traverse DAG from row source back to Income, adding a synthetic row for each edge it finds.
            #   NOTE: if using s-tags, will go back to the tag instead of Income
            # TODO: explore cases where we are multiple synthetic rows deep, or a synthetic row has been added that flows INTO income, or orphan flows (eg deductions) include synthetic nodes.
            s_tag_d1 = False
            if self._df.at[k, "Type"] == 'deduction':  # deduction types skip DAG processing for now
                self.process_report += f"[{this_step_id}] SKIPPING DAG traversal, since this is a deduction type.\n"
                if self._app_settings.verbose:
                    print(f"Skipping DAG checks as this was a deductions type entry: {this_row.Date} | {this_row.Description} | {this_row.Source} -> {this_row.Target} | ${this_row.Amount}")
                continue

            # traverse graph
            if tag_type == 's-tag' and (this_row.Source == tag_matches[0] or this_row.Target == tag_matches[0]):
                # First order edge and is s-tag - skip processing
                s_tag_d1 = True
            elif "Income" in nx.ancestors(self._labels_obj._digraph, this_row.Target):
                # Must be an expense category:
                start_node = "Income"
                end_node = this_row.Source  # This breaks if there are multiple paths to the end node, eg when using tags/stores flows
            else:
                # Must be an income category
                start_node = this_row.Source
                end_node = "Income"

            if not s_tag_d1:
                self.process_report += f"[{this_step_id}] Starting to traverse DAG for {start_node} -> {end_node}\n"
                if self._app_settings.verbose:
                    print(f"Traversing graph for {start_node}:{end_node}...")

                pgroups = [i for i in nx.all_simple_edge_paths(self._labels_obj._digraph, start_node, end_node)]
                if is_recurring:
                    new_groups = [[]]
                    for g in pgroups[0]:
                        if g[0] == "Income":
                            if self._app_settings.verbose:
                                print(f"--- Injecting Income:Recurring and Recurring:{g[1]} nodes ----")
                            new_groups[0].append(("Income", "Recurring"))
                            new_groups[0].append(("Recurring", g[1]))
                        else:
                            new_groups[0].append(g)
                    pgroups = new_groups

                self.process_report += f"[{this_step_id}] DAG search yielded groups: {pgroups}\n"
                if self._app_settings.verbose:
                    print(f"Searched DAG for {start_node} -> {end_node} and got group: {pgroups}...")
                if len(pgroups) != 1:
                    print(f"Edge paths search did not yield the expected number of groups! {pgroups}")  # Potentially an error condition. Maybe raise an exception
                for pgroup in pgroups:
                    # Each edge path will be an array of tuples, like [(source1,target1), (source2,target2), ...]
                    # Iterate over the paths (ignoring the one that matches the original entry) and create synthetic entries for each one.
                    for pitem in pgroup:
                        if pitem == (this_row.Source, this_row.Target): # Don't need to process the pair we already have
                            continue
                        syn_source, syn_target = pitem
                        if syn_source == "Income" and tag_type == 's-tag':
                            # Since this is an s-tag flow, the root of the flow should be the tag
                            syn_source = tag_matches[0]
                        if syn_target == "Income" and tag_type == 's-tag':
                            syn_target = tag_matches[0]  # TODO: verify that this case is handled as expected
                        self.process_report += f"[{this_step_id}] ADDED: {this_row.Date} | {this_row.Description} | {syn_source} -> {syn_target} | ${self._df.at[k, 'Amount']}\n"
                        if self._app_settings.verbose:
                            print(f"Adding synthetic entry: {this_row.Date} | {this_row.Description} | {syn_source} -> {syn_target} | ${self._df.at[k, 'Amount']}")
                        self.add_row(DataRow.create(
                            date=this_row.Date,
                            category_name=this_row.Category,
                            amount=self._df.at[k, "Amount"],
                            source=syn_source,
                            target=syn_target,
                            description=this_row.Description,
                            tags=this_row.Tags,
                            comment='Synthetic row',
                            distribution=this_row.Distribution
                        ), True)

            self.process_report += f"[{this_step_id}] DONE processing.\n{'-'*40}\n"

    def collapse(self):
        self.process_report += f"\n{'-'*40}\nStepping into Transactions.collapse()\n{'-'*40}\n"
        if self._app_settings.verbose:
            print("Aggregating all source-target pairs")
        # Collapse all the pairs down for cleaner flows
        grouped_df = self._df.groupby(['Source', 'Target']).agg({'Amount': 'sum'})
        grouped_df.reset_index(inplace=True)  # Resetting an index appears to just create a new one unless the drop argument is passed in, but that's fine in this case.
        self._grouped_df = grouped_df # TODO: Review grouped_df vs _df
        if self._app_settings.verbose:
            print(f"Collapsed {len(self._df)} transactions down to {len(self._grouped_df)}")

    def create_surplus_deficit_flows(self):
        self.process_report += f"\n{'-'*40}\nStepping into Transactions.create_surplus_deficit_flows()\n{'-'*40}\n"
        if self.surplus_deficit_processed:
            print("Surplus/deficit flows have already been processed!")
            return
        self.surplus_deficit_processed = True
        if self._app_settings.verbose:
            print("Computing source/deficit flows")
        # Check for s-tag nodes
        node_types = nx.get_node_attributes(self._labels_obj._digraph, 'type')  # Returns a dict like: {'a': 's-tag', 'd': 's-tag, 'c': 'tag', ...}
        s_nodes = [i for i in node_types if node_types[i] == 's-tag']  # A list of s-nodes
        s_nodes.append("Income")

        for s_node in s_nodes:
            # Create synthetic entries showing difference between flows into and out of Income as either a surplus or deficit.
            # Date should always be within the current filter range, if used.
            # TODO: review for race conditions with feed_in arg and computing surpluses
            total_income = self._df.loc[self._df["Target"] == s_node].agg({'Amount': 'sum'})["Amount"]
            total_expenses = self._df.loc[self._df["Source"] == s_node].agg({'Amount': 'sum'})["Amount"]
            if total_income > total_expenses:
                surplus = total_income - total_expenses
                if s_node != "Income" and self._app_settings.feed_in:
                    # Feeding s-tag surplus back to Income
                    self.process_report += f"ADDED: {self.default_date} | '{s_node} Surplus' | {s_node} -> 'Income' | ${surplus}\n"
                    self.add_row(DataRow.create(
                        date=self.default_date,
                        category_name=f"{s_node} Surplus",
                        amount=surplus,
                        source=s_node,
                        target=f"Income",
                        comment=f"Synthetic {s_node} surplus entry"
                    ), True)
                else:
                    # Keeping s-tag surplus(es) as distinct flow
                    self.process_report += f"ADDED: {self.default_date} | '{s_node} Surplus' | {s_node} -> '{s_node} Surplus' | ${surplus}\n"
                    self.add_row(DataRow.create(
                        date=self.default_date,
                        category_name=f"{s_node} Surplus",
                        amount=surplus,
                        source=s_node,
                        target=f"{s_node} Surplus",
                        comment=f"Synthetic {s_node} surplus entry"
                    ), True)

                # Copy 'Surplus' color information to new entry
                this_label = self._labels_obj._lookup.get("Surplus")
                if this_label:
                    this_label["source"] = {s_node}
                    this_label["target"] = f'{s_node} Surplus'
                    self._labels_obj._lookup[f'{s_node} Surplus'] = this_label

            elif total_expenses > total_income:
                # TODO: If using feed_in arg, copy Income surplus (if any) to s-tag?? (or, more accurately, s-tag deficit from income)
                deficit = total_expenses - total_income
                self.process_report += f"ADDED: {self.default_date} | '{s_node} Deficit' | '{s_node} Deficit' -> {s_node} | ${deficit}\n"
                self.add_row(DataRow.create(
                    date=self.default_date,
                    category_name=f"{s_node} Deficit",
                    amount=deficit,
                    source=f"{s_node} Deficit",
                    target=s_node,
                    comment=f"Synthetic {s_node} deficit entry"
                ), True)
                # Copy 'Deficit' color information to new entry
                this_label = self._labels_obj._lookup.get("Deficit")
                if this_label:
                    this_label["source"] = {s_node}
                    this_label["target"] = f'{s_node} Deficit'
                    self._labels_obj._lookup[f'{s_node} Deficit'] = this_label


    def filter_dates(self, start_date, end_date):
        self.process_report += f"\n{'-'*40}\nStepping into Transactions.filter_dates({start_date}, {end_date})\n{'-'*40}\n"
        # All times should be pandas._libs.tslibs.timestamps.Timestamp
        # Will discard data outside supplied daterange... TODO: preserve original df??

        if self._app_settings.verbose:
            print(f"Filtering data from {start_date} .. {end_date}...")

        if start_date is None and end_date is None:
            return  # no op.

        # Coerce to timestamp
        if type(start_date) is not timestamps.Timestamp:
            start_date = pd.to_datetime(start_date)  # pd.to_datetime(None) returns None
        if type(end_date) is not timestamps.Timestamp:
            end_date = pd.to_datetime(end_date)

        if end_date: # Set up a default date guaranteed to be within the filter range.
            self.default_date = end_date - datetime.timedelta(days=1) # One day before our end date
        elif start_date:
            self.default_date = start_date + datetime.timedelta(days=1) # One day ater our start date

        # Start or end date is unbounded, set it to the earliest (or latest) date in the fetched data.
        if not start_date:
            start_date = self.earliest_date
        if not end_date:
            end_date = self.latest_date

        if start_date > end_date:
            raise Exception(f"Start date ({start_date.date()}) is after end date ({end_date.date()})!")

        self.process_report += f">> final dates to use for filtering: {start_date} - {end_date} <<\n{'-'*60}\n"

        dt_mask = (self._df["Date"] >= start_date) & (self._df["Date"] <= end_date)  # Boolean sum of the two masks
        self._df = self._df[dt_mask]
        self._df = self._df.reset_index(drop=True)
        if len(self._df) == 0:
            raise Exception(f"Supplied date range ({start_date.date()} - {end_date.date()}) does not contain any transactions!")
        self.earliest_date = self._df["Date"].sort_values().iloc[0]
        self.latest_date = self._df["Date"].sort_values().iloc[len(self._df)-1]
        self.default_date = self.latest_date - datetime.timedelta(days=1)
        self.process_report += f"DONE filtering dates. Earliest date is: {self.earliest_date}, latest date is: {self.latest_date}, default date is: {self.default_date}, and the dataset now contains {len(self._df)} transactions.\n{'-'*60}\n"

    def explode_tags(self):
        # Split each tag out to its own column, with true/false value for a given row
        # Note: currently unused but possible future functionality around tags.
        result = {}
        unique_df_tags = [val.strip() for sublist in self._df["Tags"].str.split(",").tolist() for val in sublist]
        unique_df_tags = list(set(unique_df_tags))
        if '' in unique_df_tags:
            unique_df_tags.remove('')
        for tag in unique_df_tags:
            # TODO: fix edge case if you had a tag 'foo' and another tag 'foot' where 'foot' is marked as having 'foo'
            self._df[tag] = self._df["Tags"].str.contains(tag).to_list()

    def distribute_amounts(self):
        # Distribute a payment over a time period
        # Note: this creates synthetic transactions in the future, which will affect latest date.
        # TODO: verify that this will fall within the current date filters, if being used.
        #       current method is to just call this before filter_dates() would need to refactor to be more robust
        # TODO: handle negative values to distribute backwards (as in, a charge that represents past costs)
        if self.amount_distributions:
            print("Amounts have already been distributed!")
            return
        self.amount_distributions = True
        self.process_report += f"{'-'*60}\nRunning Transactions.distribute_amounts()\n{'-'*60}\n"
        df_idx = len(self._df)
        # Loop through dataset looking for distributed rows
        for k,v in enumerate(self._df["Distribution"]):
            if not is_empty(v, True):
                reverse_distribution = False
                v = int(v)
                if v < 0:
                    # Negative distribution
                    reverse_distribution = True
                    v = abs(v)
                original_amount = float(self._df.at[k, "Amount"]), self._df.at[k, "Sales Tax"]  # A tuple with (Amount, Sales Tax)
                original_date = self._df.at[k, "Date"]
                dist_amount = original_amount[0]/int(v)  # Calculate total amount / distributions
                dist_sales_tax = 0
                dists = []
                if not is_empty(original_amount[1], True):
                    dist_sales_tax = float(original_amount[1])/int(v) # Calculate sales tax amount / distributions
                # Reset original transaction to distirbution amount
                self.process_report += f"UPDATED: {self._df.at[k, 'Date']} | {self._df.at[k, 'Description']} | {self._df.at[k, 'Source']} -> {self._df.at[k, 'Target']} | ${dist_amount} (+ ${dist_sales_tax})\n"
                self._df.at[k, "Amount"] = dist_amount
                self._df.at[k, "Sales Tax"] = dist_sales_tax
                # Create Synthetic entries for distributed transactions
                counter = v
                while counter > 1:  # Don't need to do the first one, as we changed it in place
                    if reverse_distribution:
                        new_date = original_date - datetime.timedelta(weeks=(counter-1)*4.33)  # We assume that the distrubtion value is in months.
                    else:
                        new_date = original_date + datetime.timedelta(weeks=(counter-1)*4.33)  # We assume that the distrubtion value is in months.
                    self.process_report += f"ADDED: {new_date} | {self._df.at[k, 'Description']} | {self._df.at[k, 'Source']} -> {self._df.at[k, 'Target']} | ${dist_amount} (+ ${dist_sales_tax})\n"
                    # create(date, category_name, source, target, amount, description="", sales_tax=0, tips=0, comment="", tags="", row_type="", distribution=0):
                    # Assuming no tips on distributed transactions for now
                    dists.append(DataRow.create(
                        new_date,
                        self._df.at[k, "Category"],
                        self._df.at[k, "Source"],
                        self._df.at[k, "Target"],
                        dist_amount,
                        self._df.at[k, "Description"],
                        dist_sales_tax,
                        0,
                        f"Synthetic transaction from original transaction on {original_date} of {original_amount[0]} (+{original_amount[1]})",
                        self._df.at[k, "Tags"],
                        self._df.at[k, "Type"],
                        0
                    ))
                    counter -= 1
                for row in dists:
                    self._df.loc[df_idx] = row  # Add check_data_row here?
                    df_idx += 1
            self.latest_date = self._df["Date"].sort_values()[len(self._df)-1]  # Reset latest date value

    def update_title(self):
        # TODO: add flag information to title
        self.title = f"{self._app_settings.base_title} ({self.earliest_date.month}/{self.earliest_date.day}/{self.earliest_date.year} - {self.latest_date.month}/{self.latest_date.day}/{self.latest_date.year})"
        if self._app_settings.distribute_amounts:
            self.title += "<br>    Multi-month transactions are being distributed"
        if self._app_settings.exclude_tags:
            self.title += f"<br>    Tags being excluded: {', '.join(self._app_settings.exclude_tags)}"
        if self._app_settings.tags:
            self.title += f"<br>    Tags being used: {', '.join(self._app_settings.tags)}"
        if self._app_settings.recurring:
            self.title += f"<br>    Recurring transactions are being split out"


class TransactionRow:
    def __init__(self, df, key):
        self.key = key
        self.data = {}
        for col in DataRow.fields:
            val = df.at[key, col]
            if is_null(val) and DataRow.fields[col]["required"]:
                raise Exception(f"Required column {col} was null for {repr(df[key])}")
            self.data[col] = val

    class TransactionDate:
        def __init__(self, value):
            self._required = True
            self._nullable = True
            self._datatype = timestamps.Timestamp
            self._coerce_type = True  # TODO: switch to a function that coerces. Or just use getters and setters.
            self._comment = ""
            self._value = pd.to_datetime(value)

        @property
        def value(self):
            return self._value

        @value.setter
        def value(self, val):
            self._value = pd.to_datetime(val)




class DataRow:
    # static class - just a container for some related methods around single rows of expense data.
    fields = {
        "Date": {
            "required": True,
            "nullable": False,
            "type": timestamps.Timestamp,
            "force_type": False,
            "comment": ""
        },
        "Category": {
            "required": True,
            "nullable": False,
            "type": str,
            "force_type": False,
            "comment": ""
        },
        "Description": {
            "required": False,
            "nullable": True,
            "type": str,
            "force_type": False,
            "comment": ""
        },
        "Tags": {
            "required": False,
            "nullable": True,
            "type": str,
            "force_type": False,
            "comment": ""
        },
        "Comments": {
            "required": False,
            "nullable": True,
            "type": str,
            "force_type": False,
            "comment": ""
        },
        "Source": {
            "required": False,
            "nullable": True,
            "type": str,
            "force_type": False,
            "comment": ""
        },
        "Target": {
            "required": False,
            "nullable": True,
            "type": str,
            "force_type": False,
            "comment": ""
        },
        "Type": {
            "required": False,
            "nullable": True,
            "type": str,
            "allowed_values": ["computed", "tag", ""],
            "force_type": False,
            "comment": ""
        },
        "Distribution": {
            "required": False,
            "nullable": True,
            "type": int,
            "force_type": True,
            "comment": "Value in whole months to distribute the row amount over"
        },
        "Amount": {
            "required": True,
            "nullable": False,
            "type": float,
            "force_type": True,
            "comment": ""
        },
        "Sales Tax": {
            "required": False,
            "nullable": True,
            "type": float,
            "force_type": True,
            "comment": ""
        },
        "Tips": {
            "required": False,
            "nullable": True,
            "type": float,
            "force_type": True,
            "comment": ""
        }
    }

    @staticmethod
    def validate(drow, header_only=False):
        # Validate that data rows are correct
        if len(drow) != len(DataRow.fields):
            raise Exception(f"Data rows should contain {len(DataRow.fields)} elements")
        if header_only:
            if drow != list(DataRow.fields.keys()):
                return False, f"Data rows need to be in the form: {list(DataRow.fields.keys())}"
            return True, None
        vkeys = list(DataRow.fields.keys())
        counter = 0
        while counter < len(drow):
            this_validator = DataRow.fields[vkeys[counter]]
            this_value = drow[counter]
            counter += 1
            if is_null(this_value):  # Also check for length = 0?
                if this_validator["nullable"]:
                    pass
                else:
                    raise Exception(f"Non-nullable field {vkeys[counter-1]} was nulled in {drow}")
            else:
                if type(this_value) != this_validator["type"]:
                    if this_validator["force_type"]:
                        try:
                            this_value = this_validator["type"](this_value)
                        except ValueError:
                            raise Exception(f"Could not coerce \'{this_value}\' at idx {counter - 1} to {this_validator['type']} for this row: {drow}")
                if type(this_value) != this_validator["type"]:
                    raise Exception(f"Invalid type at idx {counter - 1} for {this_value} in {drow}")
                if this_validator.get("allowed_values") and this_value not in this_validator["allowed_values"]:
                    raise Exception(f"Non-allowed value of {this_value} in {drow}")
        return drow

    @staticmethod
    def create(date, category_name, source, target, amount, description="", sales_tax=0, tips=0, comment="", tags="", row_type="", distribution=0):
        if is_null(amount):
            amount = 0
        else:
            try:
                amount = float(amount)
            except ValueError:
                amount = 0
        if is_null(tips):
            tips = 0
        else:
            try:
                tips = float(tips)
            except ValueError:
                tips = 0
        if is_null(distribution):
            distribution = 0
        else:
            try:
                distribution = int(distribution)
            except ValueError:
                distribution = 0
        if is_null(sales_tax):
            sales_tax = 0
        else:
            try:
                sales_tax = float(sales_tax)
            except ValueError:
                sales_tax = 0
        return DataRow.validate([date, category_name, description, tags, comment, source, target, row_type, distribution, amount, sales_tax, tips])

    @staticmethod
    def tag_matches(row_tags, search_tags):
        # Tag logic
        this_exploded_tags = None
        this_tag_matches = None
        this_store_matches = False
        if search_tags and not is_empty(search_tags) and not is_empty(row_tags):
            this_exploded_tags = [i.strip() for i in row_tags.split(',')]  # TODO: Do this case insensitively?
            if this_exploded_tags:
                return [i for i in set(search_tags).intersection(set(this_exploded_tags))]
        return None


# Define some helper functions ==============================================================================================

def is_null(obj):
    # Just using numpy.isnan() will throw errors for types that cannot be coerced to float64. Could also use a try...catch
    # use as a general purpose null/none/NaN catch
    if obj is None:
        return True
    if type(obj) is float64 and isnan(obj):
        return True
    if type(obj) is nattype.NaTType:
        return True
    obj_as_str = None
    try:
        obj_as_str = str(obj)
    except:
        pass
    if obj_as_str in ["None", "none", "NaN", "nan", "Null", "null"]:
        return True
    return False

def is_empty(obj, nonzero=False):
    # Check for null, nan, none, etc as well as empty string. Optionally check for zero values. Swallow errors casting to values
    if is_null(obj):
        return True
    obj_as_str = None
    try:
        obj_as_str = str(obj)
    except:
        pass
    if obj_as_str == "":
        return True
    if nonzero:
        obj_as_float = None  # int() truncates values like 0.25 to 0
        try:
            obj_as_float = float(obj)
        except:
            pass
        if obj_as_float == 0:
            return True
    return False

def save_report(report_data, basename):
    dtnow = pd.Timestamp.today()
    fname = f"{basename}-{dtnow}.txt"
    if path.isfile(fname):
        raise Exception(f"File named {fname} already exists!")
    with open(fname, 'wt') as f:
        f.write(report_data)


def validate_date_string(input, allow_empty=False):
    # Pandas will accept YYYY-MM-DD or MM/DD/YYYY
    if is_empty(input, True) and allow_empty:
        return True
    match_obj = re.match("^([\d]{4})-([\d]{1,2})-([\d]{1,2})$", input)
    if match_obj:
        match_year = int(match_obj.groups()[0])
        match_month = int(match_obj.groups()[1])
        match_day = int(match_obj.groups()[2])
    else:
        match_obj = re.match("^([\d]{1,2})/([\d]{1,2})/([\d]{4})$", input)
        if match_obj:
            match_year = int(match_obj.groups()[2])
            match_month = int(match_obj.groups()[0])
            match_day = int(match_obj.groups()[1])
    if match_obj:
        if not (1900 < match_year < 2100):  # Update if doing historical work!
            print(f"Supplied year doesn\t look right: {match_year}")
            return False
        if not (1 <= match_month <= 12):
            print(f"Invalid month value: {match_month}")
            return False
        if not (1 <= match_day <= 31):
            print(f"Invalid day value: {match_day}")
            return False
        return True
    return False

def func_Convert_Gsheet_dates(g_timestamp, default_date):
    # Note: currently unused
    if g_timestamp:
        try:
            g_timestamp_as_int = int(g_timestamp)
            # Likely means we got an unformatted timestamp from gsheets.
            # See also: https://developers.google.com/sheets/api/guides/formats for information about Google sheets timestamp format
            # See: http://www.cpearson.com/excel/datetime.htm for why Dec 30, 1899
            return pd.to_datetime(g_timestamp_as_int * 86400*1000, unit='ms', origin="1899-12-30")
        except ValueError:
            # We'll assume this means we got a formatted date string
            return pd.to_datetime(g_timestamp)
    else:
        if not default_date:
            return pd.Timestamp.today()
        return pd.to_datetime(default_date) # default_date

def fetch_data(app_settings_obj):  # source_spreadsheet, source_worksheet, csv_src_target, service_account_credentials):
    # app_settings_obj.data_source, app_settings_obj.data_sheet, app_settings_obj.labels_source, app_settings_obj.g_creds
    try:
        if app_settings_obj.data_source.endswith(".csv"):
            # See sample_data/expenses.csv and labels.csv for examples of data format.
            # TODO: validation & error handling
            if not app_settings_obj.labels_source or not app_settings_obj.labels_source.endswith('.csv'):
                app_settings_obj.labels_source = input("Enter location for sources-targets CSV data: ")
            if not app_settings_obj.labels_source.endswith('.csv') or not path.isfile(app_settings_obj.labels_source):
                raise Exception(f"Supplied sources-targets file ({app_settings_obj.labels_source}) was not found or is the wrong format.")
            if not app_settings_obj.data_source.endswith('.csv') or not path.isfile(app_settings_obj.data_source):
                raise Exception(f"Supplied transactions file ({app_settings_obj.data_source}) was not found or is the wrong format.")
            with open(app_settings_obj.labels_source, 'r') as f:
                dr = DictReader(f)
                src_target = list(dr)
            df = pd.read_csv(app_settings_obj.data_source)
        else:
            gc = pygsheets.authorize(service_file=app_settings_obj.g_creds)
            if app_settings_obj.data_source not in gc.spreadsheet_titles():
                raise Exception(f"Requested spreadsheet ({app_settings_obj.data_source}) is not available to configured service account (see: '{app_settings_obj.g_creds}')")
            sh = gc.open(app_settings_obj.data_source) # TODO: error handling
            sh_titles = [i.title for i in sh.worksheets()]
            if app_settings_obj.labels_source not in sh_titles:
                raise Exception(f"Sources-Targets worksheet \'{app_settings_obj.labels_source}\' was not found in {app_settings_obj.data_source}!")
            if app_settings_obj.data_sheet not in sh_titles:
                raise Exception(f"Data worksheet '{app_settings_obj.data_sheet}' was not found in {app_settings_obj.data_source}!")
            src_target = sh.worksheet_by_title(app_settings_obj.labels_source).get_all_records()  # Fetch source-target info and colors.
            df = sh.worksheet_by_title(app_settings_obj.data_sheet).get_as_df() #value_render=pygsheets.ValueRenderOption.UNFORMATTED_VALUE) # <-- Using unformatted value rounded decimal amounts - not sure why
    except Exception as e:
        print(f"Unable to open data source: {app_settings_obj.data_source}. Please check your names and try again. Error was {e}")
        raise SystemExit

    # Clean up value formatting
    df = df.transform(normalize_amounts, axis=1)

    is_valid = DataRow.validate(df.columns.to_list(), True)
    if not is_valid[0]:
        raise Exception(f"Source data is not in correct format! Message was: {is_valid[1]}")

    return src_target, df

def normalize_amounts(df_row):
    for atype in ["Amount", "Sales Tax", "Tips"]:
        val = df_row[atype]
        if is_empty(val):
            continue
        try:
            val = float(val)
        except ValueError:
            if '$' in val or ',' in val:
                val = float(val.replace('$','').replace(',',''))
        df_row[atype] = val
    return df_row
