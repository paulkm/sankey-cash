import logging
import re
from os import path
from typing import Optional

import pandas as pd
from numpy import float64, isnan
from pandas._libs.tslibs import nattype

# Shared package-level logger. Submodules use `logging.getLogger(__name__)` and propagate up to
# this handler rather than each attaching their own - AppSettings' --verbose handling
# (logger.setLevel(...)) relies on there being exactly one logger/handler pair for the whole
# package.
logger = logging.getLogger("sankey_cashflow")
_console_handler = logging.StreamHandler()
# TODO: override this with params (note: root logger level will also need to be changed)
_console_handler.setLevel(logging.WARNING)
_console_handler.name = "console"
logger.addHandler(_console_handler)


def is_null(obj: any) -> bool:
    # Just using numpy.isnan() will throw errors for types that cannot be coerced to float64.
    # Could also use a try...catch
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
    except Exception:
        pass
    if obj_as_str in ["None", "none", "NaN", "nan", "Null", "null"]:
        return True
    return False


def is_empty(obj: any, nonzero: Optional[bool] = False) -> bool:
    # Check for null, nan, none, etc as well as empty string. Optionally check for zero values.
    # Swallow errors casting to values
    if is_null(obj):
        return True
    obj_as_str = None
    try:
        obj_as_str = str(obj)
    except Exception:
        pass
    if obj_as_str == "":
        return True
    if nonzero:
        obj_as_float = None  # int() truncates values like 0.25 to 0
        try:
            obj_as_float = float(obj)
        except Exception:
            pass
        if obj_as_float == 0:
            return True
    return False


def df_date_filter(df, start_date, end_date):
    # Filter a dataframe by date
    if is_empty(start_date) and is_empty(end_date):
        return df
    if is_empty(start_date):
        df = df[df["Date"] <= end_date]
    elif is_empty(end_date):
        df = df[df["Date"] >= start_date]
    else:
        df = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
    df = df.reset_index(drop=True)
    if len(df) == 0:
        # TODO: this will error if start_date or end_date are not dates
        raise Exception(f"Supplied date range ({start_date.date()} - {end_date.date()}) does not contain any \
                        transactions!")
    return df


def save_report(report_data, basename):
    dtnow = pd.Timestamp.today()
    fname = f"{basename}-{dtnow}.txt"
    if path.isfile(fname):
        raise Exception(f"File named {fname} already exists!")
    with open(fname, 'wt') as f:
        f.write(report_data)


def validate_date_string(input, allow_empty=False):
    # Pandas will accept YYYY-MM-DD or MM/DD/YYYY
    if is_empty(input, True):
        if allow_empty:
            return True
        else:
            raise Exception("Date string cannot be empty!")
    match_obj = re.match(r"^([\d]{4})-([\d]{1,2})-([\d]{1,2})$", input)
    if match_obj:
        match_year = int(match_obj.groups()[0])
        match_month = int(match_obj.groups()[1])
        match_day = int(match_obj.groups()[2])
    else:
        match_obj = re.match(r"^([\d]{1,2})/([\d]{1,2})/([\d]{4})$", input)
        if match_obj:
            match_year = int(match_obj.groups()[2])
            match_month = int(match_obj.groups()[0])
            match_day = int(match_obj.groups()[1])
    if match_obj:
        if not (1900 < match_year < 2100):  # Update if doing historical work!
            logger.warning(f"Supplied year doesn\t look right: {match_year}")
            return False
        if not (1 <= match_month <= 12):
            logger.warning(f"Invalid month value: {match_month}")
            return False
        if not (1 <= match_day <= 31):
            logger.warning(f"Invalid day value: {match_day}")
            return False
        return True
    return False


def normalize_amounts(df_row):
    for atype in ["Amount", "Sales Tax", "Tips"]:
        val = df_row[atype]
        if is_empty(val):
            continue
        try:
            val = float(val)
        except ValueError:
            if '$' in val or ',' in val:
                val = float(val.replace('$', '').replace(',', ''))
        df_row[atype] = val
    return df_row
