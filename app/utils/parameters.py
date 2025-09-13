"""Utility functions for parameter parsing and conversion."""

from typing import List, Optional

def csv_to_list(value: Optional[str]) -> Optional[List[str]]:
    """
    Convert a comma-separated string to a list of strings.
    Trims whitespace and ignores empty items.
    :param value: Comma-separated string or None
    :return:
    """
    if value is None:
        return None
    items = [x.strip() for x in value.split(",")]
    out = [x for x in items if x]
    return out or None
