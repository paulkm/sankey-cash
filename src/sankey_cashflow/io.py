from csv import DictReader
from os import path
from pathlib import Path
from typing import Union

import pandas as pd
import pygsheets

from .data_row import DataRow
from .utils import logger, normalize_amounts


def fetch_data(app_settings_obj):  # source_spreadsheet, source_worksheet, csv_src_target, service_account_credentials):
    # app_settings_obj.data_source,app_settings_obj.data_sheet,app_settings_obj.labels_source,app_settings_obj.g_creds
    # WIP: Handle source data in mutiple sheets, eg. 1 sheet per year...

    """
        self.data_source = args.source  # A csv file or a google Sheets document containing transactions data.
            (In the case of the latter, a sheet name must be provided as well)
        self.data_sheet = args.sheet or "Transactions_*"  # The name (or prefix plus wildcard) of the sheet containing
            the transactions data (if data_source is a google Sheets document
        self._labels_source = args.srcmap or "Sources-Targets" #A csv file or sheet name containing sources and targets
    """
    def data_source_router(
            filename: str,
            file_kind: str,
            gcreds,
            sheetname: Union[str, None] = None,
            gcreds_obj=None,
            gsheets_obj=None):
        """
        Calls itself recursively, looking for data sources either locally or in Google Sheets and returns the first hit.
            Handle wildcards expressions for multiple sheets.
            Return a dict containing a list of filenames.
        :param filename: A filename or wildcard expression, or None (Note: only csv files will use the wildcard
            expression for this value)
        :param file_kind: "sources-targets" or "transactions"
        :param gcreds: Google credentials object
        :param sheetname: A sheet name or wildcard expression, or None (only applicable to Google Sheets)
        :param gc: Google client object (optional)

        Returns: {
            "filename" -> list of strings,
            "sheetname" -> list of strings,
            "filetype" -> ["csv", "gsheet"],
            "file_kind" -> ["sources-targets","transactions"],
            "gcreds_obj" -> Google credentials object",
            "gsheets_obj" -> Google sheets object
        }
        """
        file_kind = file_kind.lower()
        if file_kind not in ["sources-targets", "transactions"]:
            raise Exception(f"Invalid file kind: {file_kind}")
        if filename is None:
            filename = input(f"Enter location for {file_kind} data: ")
            return data_source_router(filename, file_kind, gcreds, sheetname, gcreds_obj, gsheets_obj)
        if filename.endswith(".csv"):
            if path.isfile(filename):  # Switch to pathlib?
                return {
                    "filename": [filename],
                    "sheetname": [None],
                    "filetype": "csv",
                    "file_kind": file_kind,
                    "gcreds_obj": gcreds_obj,
                    "gsheets_obj": gsheets_obj}
            logger.warning(f"File not found: {filename}")
            return data_source_router(None, file_kind, gcreds, sheetname, gcreds_obj, gsheets_obj)
        if filename.endswith("*"):
            # Wildcards on filenames only supported for csvs, Gsheets would use sheetnames for wildcard.
            fileparts = filename.split("/")
            filepattern = f"{fileparts[-1]}.csv"
            if len(fileparts[0]) == 0:
                # This must be an absolute path
                this_dir = "/" + "/".join(fileparts[1:-1])
            else:
                # Possibly a relative path
                if len(fileparts) > 1:
                    this_dir = "./" + "/".join(fileparts[:-1])
                else:
                    this_dir = "."
            dir_obj = Path(this_dir)
            if dir_obj.is_dir():
                files = list(dir_obj.glob(filepattern))
                if len(files) > 0:
                    return {"filename": [str(f) for f in files],
                            "sheetname": [None],
                            "filetype": "csv",
                            "file_kind": file_kind,
                            "gcreds_obj": gcreds_obj,
                            "gsheets_obj": gsheets_obj}
            logger.warning("No files found at: {filename}")
            return data_source_router(None, file_kind, gcreds, sheetname, gcreds_obj, gsheets_obj)
        # If we've gotten this far, we must be looking for a Google Sheets file (late binding of the
        # gc object to reduce calls to authorize)
        if not gcreds_obj:
            gcreds_obj = pygsheets.authorize(service_file=gcreds)  # trying to avoid calling this multiple times
        if filename not in gcreds_obj.spreadsheet_titles():
            logger.warning(f"Spreadsheet not found: {filename}")
            return data_source_router(None, file_kind, gcreds, sheetname, gcreds_obj, gsheets_obj)
        gsheets_obj = gcreds_obj.open(filename)  # TODO: error handling.
        if not sheetname:
            sheetname = input(f"Enter worksheet title for spreadsheet {filename}: ")
            return data_source_router(filename, file_kind, gcreds, sheetname, gcreds_obj, gsheets_obj)
        gsheet_titles = [i.title for i in gsheets_obj.worksheets()]
        if sheetname.endswith("*"):
            # Wildcard handling for sheetnames
            results = []
            for sheet in gsheet_titles:
                if sheet.startswith(sheetname[:-1]):
                    results.append(sheet)
            if len(results) > 0:
                return {
                    "filename": [filename],
                    "sheetname": results,
                    "filetype": "gsheet",
                    "file_kind": file_kind,
                    "gcreds_obj": gcreds_obj,
                    "gsheets_obj": gsheets_obj}
            logger.warning(f"No spreadsheets found matching pattern: \"{sheetname}\" in Google Sheets: \"{filename}\"")
            return data_source_router(filename, file_kind, gcreds, None, gcreds_obj, gsheets_obj)
        if sheetname in gsheet_titles:
            return {"filename": [filename],
                    "sheetname": [sheetname],
                    "filetype": "gsheet",
                    "file_kind": file_kind,
                    "gcreds_obj": gcreds_obj,
                    "gsheets_obj": gsheets_obj}
        logger.warning(f"Spreadsheet \"{sheetname}\" not found in Google Sheets: \"{filename}\"")
        return data_source_router(filename, file_kind, gcreds, None, gcreds_obj, gsheets_obj)

    try:
        # Get sources-targets file location data
        # See sample_data/expenses.csv and labels.csv for examples of data format.
        # TODO: validation & error handling
        # TODO: there should only ever be one sources-targets file, so data_source_router should handle that
        src_target = None
        if app_settings_obj.labels_source.endswith(".csv"):
            src_target_file = data_source_router(app_settings_obj.labels_source,
                                                 "sources-targets",
                                                 app_settings_obj.g_creds, None, None, None)
        else:
            src_target_file = data_source_router(app_settings_obj.data_source,
                                                 "sources-targets",
                                                 app_settings_obj.g_creds,
                                                 app_settings_obj.labels_source, None, None)
        if src_target_file["filetype"] == "csv":
            # Sources-targets data is returned differently than transactions data, so we need to handle it differently.
            with open(src_target_file["filename"][0], 'r') as f:
                dr = DictReader(f)
                src_target = list(dr)
        else:
            # Fetch source-target info and colors.
            src_target = src_target_file["gsheets_obj"].\
                worksheet_by_title(src_target_file["sheetname"][0]).get_all_records()

        # Get transactions file(s) location data
        df = None
        transaction_data_file = data_source_router(app_settings_obj.data_source,
                                                   "transactions",
                                                   app_settings_obj.g_creds,
                                                   app_settings_obj.data_sheet, None, None)
        if transaction_data_file["filetype"] == "csv":
            # open one or multiple csv files and return a pandas dataframe
            df = read_csv_as_df(transaction_data_file["filename"])
        else:
            # Open one or multiple gsheet worksheets and return a pandas dataframe
            df = read_gsheet_as_df(transaction_data_file["sheetname"], transaction_data_file["gsheets_obj"])

    except Exception as e:
        logger.error(f"Unable to open data source: {app_settings_obj.data_source}. \
                     Please check your names and try again. Error was {e}")
        raise SystemExit

    # Clean up value formatting
    df.reset_index(inplace=True, drop=True)
    df = df.transform(normalize_amounts, axis=1)

    is_valid = DataRow.validate(df.columns.to_list(), True)
    if not is_valid[0]:
        raise Exception(f"Source data is not in correct format! Message was: {is_valid[1]}")

    return src_target, df


def read_csv_as_df(csv_file):
    if type(csv_file) is list:
        main_csv = csv_file[0]
        addl_csvs = csv_file[1:]
    else:
        main_csv = csv_file
        addl_csvs = []
    if not main_csv.endswith('.csv') or not path.isfile(main_csv):
        raise Exception(f"Supplied CSV file ({main_csv}) was not found or is the wrong format.")
    main_df = pd.DataFrame(pd.read_csv(main_csv))
    for i in addl_csvs:
        if not i.endswith('.csv') or not path.isfile(i):
            raise Exception(f"Supplied CSV file ({i}) was not found or is the wrong format.")
        add_df = pd.DataFrame(pd.read_csv(i))
        main_df = pd.concat([main_df, add_df], axis=0)
    return main_df


def read_gsheet_as_df(gsheet_file, gsheet_obj):
    # .get_as_df(value_render=pygsheets.ValueRenderOption.UNFORMATTED_VALUE)
    # # <-- Using unformatted value rounded decimal amounts - not sure why
    if type(gsheet_file) is list:
        main_sheet = gsheet_file[0]
        addl_sheets = gsheet_file[1:]
    else:
        main_sheet = gsheet_file
        addl_sheets = []
    main_df = gsheet_obj.worksheet_by_title(main_sheet).get_as_df()
    for i in addl_sheets:
        add_df = gsheet_obj.worksheet_by_title(i).get_as_df()
        main_df = pd.concat([main_df, add_df], axis=0)
    return main_df
