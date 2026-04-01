from __future__ import annotations

import re

import pandas as pd


def address_flag_list(data: pd.DataFrame, street_name: str, house_number_column: str) -> dict[str, list[str]]:
    """Create list divided into three vectors: streets with numbers, address number with dash and slasher.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contains address information.
    street_name : str
        Column name that points to the street name.
    house_number_column : str
        Column name that points to the number in address.

    Returns
    -------
    Dict[str, List[str]]
        List of three vectors containing:
        - street_with_number: streets with numbers in their names
        - numer_with_dash: address numbers containing dash
        - slasher_numer: address numbers containing slasher

    Details
    -------
    In cleaning procedure is needed information when street's name or address number,
    which contain unusual symbols are in fact correct.
    """
    ulice = data[street_name].unique()
    street_with_number = [s for s in ulice if re.search(r"\d", str(s))]

    addr_numb = data[house_number_column].unique()
    numer_with_dash = [n for n in addr_numb if "-" in str(n)]
    slasher_numer = [n for n in addr_numb if "/" in str(n)]

    return {
        "street_with_number": street_with_number,
        "numer_with_dash": numer_with_dash,
        "slasher_numer": slasher_numer,
    }
