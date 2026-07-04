from pandas._libs.tslibs import timestamps

from .utils import is_empty, is_null


class DataRow:
    # static class - just a container for some related methods around single rows of expense data.
    # The columns we expect to see in the data
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
    def validate(drow, header_only=False, include_classifications=False):
        # Validate that data rows are correct
        this_fields = DataRow.fields.copy()  # prevent mutation of the class fields
        if include_classifications:
            # Add classification to the fields
            this_fields["Classification"] = {
                "required": True,
                "nullable": False,
                "type": str,
                "force_type": False,
                "comment": ""
            }
        if len(drow) != len(this_fields):
            # import pdb; pdb.set_trace()
            raise Exception(f"Data rows should contain {len(DataRow.fields)} elements")
        if header_only:
            if drow != list(this_fields.keys()):
                return False, f"Data rows need to be in the form: {list(this_fields.keys())}"
            return True, None
        vkeys = list(this_fields.keys())
        counter = 0
        while counter < len(drow):
            this_validator = this_fields[vkeys[counter]]  # TODO: verify if this needs a copy
            this_value = drow[counter]
            counter += 1
            if is_null(this_value):  # Also check for length = 0?
                if this_validator["nullable"]:
                    pass
                else:
                    raise Exception(f"Non-nullable field {vkeys[counter - 1]} was nulled in {drow}")
            else:
                if type(this_value) is not this_validator["type"]:
                    if this_validator["force_type"]:
                        try:
                            this_value = this_validator["type"](this_value)
                        except ValueError:
                            raise Exception(f"Could not coerce \'{this_value}\' at idx {counter - 1} to \
                                            {this_validator['type']} for this row: {drow}")
                if type(this_value) is not this_validator["type"]:
                    raise Exception(f"Invalid type at idx {counter - 1} for {this_value} in {drow}")
                if this_validator.get("allowed_values") and this_value not in this_validator["allowed_values"]:
                    raise Exception(f"Non-allowed value of {this_value} in {drow}")
        return drow

    @staticmethod
    def create(
            date,
            category_name,
            source, target,
            amount,
            description="",
            sales_tax=0,
            tips=0,
            comment="",
            tags="",
            row_type="",
            distribution=0,
            classification="Uncategorized"):
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
        return DataRow.validate([
            date,
            category_name,
            description,
            tags,
            comment,
            source,
            target,
            row_type,
            distribution,
            amount,
            sales_tax,
            tips,
            classification], False, True)

    @staticmethod
    def tag_matches(row_tags, search_tags):
        # Tag logic
        this_exploded_tags = None
        if search_tags and not is_empty(search_tags) and not is_empty(row_tags):
            this_exploded_tags = [i.strip() for i in row_tags.split(',')]  # TODO: Do this case insensitively?
            if this_exploded_tags:
                return [i for i in set(search_tags).intersection(set(this_exploded_tags))]
        return None
