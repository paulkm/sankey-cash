import logging
from os import path
from typing import Union

import pandas as pd

from .utils import logger


class AppSettings:
    """
      Application settings and defaults + validation, getters/setters, etc
    """
    def __init__(self, args):
        # args will be from argparser
        self.DEFAULT_START_DATE = pd.to_datetime("10/1/2022")
        # A csv file or a google Sheets document containing transactions data.
        # (In the case of the latter, a sheet name must be provided as well)
        self.data_source = args.source
        self.audit_mode = args.audit
        # The name (or prefix plus wildcard) of the sheet containing the transactions data
        # (if data_source is a google Sheets document
        self.data_sheet = args.sheet or "Transactions_*"
        # A csv file or sheet name containing sources and targets
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
        self.hover = "Category"
        self.chart_resolution = None
        self.sales_tax_classification = "Taxes"
        self.tip_classification = "xTips"
        self.diagram_type = "sankey"
        if args.verbose:
            logger.setLevel(logging.DEBUG)
            logger.handlers[0].setLevel(logging.DEBUG)  # Assumes only one handler
        if args.hover:
            if args.hover.lower() in ["desc", "stores", "description"]:
                self.hover = "Description"
            if args.hover == "tags":
                logger.warning("Tags in hovertext not yet implemented!")
            if args.hover.lower() in ["none", "no", "false"]:
                self.hover = None
        if args.dtype:
            if args.dtype.lower() in ["sankey", "line"]:
                self.diagram_type = args.dtype.lower()
            else:
                logger.warning(f"Unknown diagram type: {args.dtype}")
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
    def date_filter_start(self) -> Union[pd.Timestamp, None]:
        return self._date_filter_start

    @date_filter_start.setter
    def date_filter_start(self, val: str) -> None:
        if not val or len(val) == 0:
            self._date_filter_start = None
        else:
            self._date_filter_start = pd.to_datetime(val)

    @property
    def date_filter_end(self) -> Union[pd.Timestamp, None]:
        return self._date_filter_end

    @date_filter_end.setter
    def date_filter_end(self, val: str) -> None:
        if not val or len(val) == 0:
            self._date_filter_end = None
        else:
            self._date_filter_end = pd.to_datetime(val)

    @property
    def g_creds(self) -> str:
        return self._g_creds

    @g_creds.setter
    def g_creds(self, val: str) -> None:
        if not val or len(val) == 0 or not path.isfile(val):
            raise Exception(f"Credentials file not found: {val}")
        self._g_creds = val

    @property
    def labels_source(self) -> str:
        return self._labels_source

    @labels_source.setter
    def labels_source(self, val: str) -> None:
        if not val or len(val) == 0 or (val.endswith('.csv') and not path.isfile(val)):
            raise Exception(f"Sources-targets file not found: {val}")
        self._labels_source = val

    def source_data_location(self) -> str:
        if self.data_source.endswith('.csv'):
            return self.data_source
        else:
            return f"{self.data_source}: {self.data_sheet}"

    def validate_sources(self) -> None:
        # check sources etc
        if not self.data_source or len(self.data_source) == 0:
            logger.warning("Please enter a valid data source!")
            raise Exception("Missing data source.")

        if self.data_source.endswith(".csv"):
            logger.debug(f"Using csv data source: {self.data_source}")
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
            logger.debug(f"Using Google Sheets data source: {self.data_source}")
            if not self.data_sheet or len(self.data_sheet) == 0:
                raise Exception("Missing Google worksheet name.")
            if not self.labels_source or len(self.labels_source) == 0:
                raise Exception("A sources-targets sheet name must be supplied.")
            if not self.g_creds or len(self.g_creds) == 0:
                raise Exception("Google service account credentials must be provided.")
            if not path.isfile(self.g_creds):
                raise Exception(f"Invalid service account credential file provided: {self.g_creds}")
