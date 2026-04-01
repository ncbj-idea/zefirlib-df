from __future__ import annotations

import logging
import re
import string
from collections.abc import Iterable

import numpy as np
import pandas as pd

from datafusion.ceeb_bdot_merger.exceptions import AddressParsingError
from datafusion.ceeb_bdot_merger.regex_patterns import (
    DashPatterns,
    ExtractionPatterns,
    HouseNumberPatterns,
    SlashPatterns,
    StreetPatterns,
)
from datafusion.configs.merge_config import BdotParams, CeebParams

_logger = logging.getLogger(__name__)


# -----------------------------
# Module-level constants
# -----------------------------

# Threshold for warning about excessive letter removals
EXCESSIVE_LETTERS_WARNING_THRESHOLD = 100

PROTECTED_STREET_NAMES_WITH_NUMBERS = [
    "dywizjonu 303",
    "303 dywizjonu",
]


def _generic_duplicator(
    data: pd.DataFrame,
    property_number_var: str,
    pattern: str,
    processor_fn: callable,
    duplication_id: str,
    id_prefix: str,
    log_file: bool = False,
) -> pd.DataFrame:
    """Generic duplicator that handles the common pattern across all duplication functions.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing address information.
    property_number_var : str
        Column name that points to the address number.
    pattern : str
        Regex pattern to detect records that need duplication.
    processor_fn : callable
        Function that takes a single-row DataFrame and property_number_var,
        returns a DataFrame with replicated rows.
    duplication_id : str
        Column name for duplication identifier.
    id_prefix : str
        Prefix for duplication_id values (e.g., "comma", "dash", "and").
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with records replicated based on the pattern.
    """
    df = data.copy()

    if log_file:
        _logger.info(f"Starting duplicated_by_{id_prefix}")

    state_to_modify = df[property_number_var].str.contains(pattern, na=False, regex=True)
    data_to_modify = df[state_to_modify].copy()
    data_to_keep = df[~state_to_modify].copy()
    rows_to_mod = len(data_to_modify)

    if rows_to_mod != 0:
        repaired_data = []

        for idx, row in data_to_modify.iterrows():
            try:
                result_df = processor_fn(pd.DataFrame([row]), property_number_var)
                repaired_data.append(result_df)
            except Exception as e:
                if log_file:
                    _logger.info(f"Error processing row {idx}: {e}")

        if repaired_data:
            for i, df_part in enumerate(repaired_data):
                df_part[duplication_id] = f"{id_prefix}_{i + 1}"

            data_to_modify = pd.concat(repaired_data, ignore_index=True)

            if log_file:
                _logger.info(f"Number of observation to modified: {rows_to_mod}")
                _logger.info(f"Number of observation after replication: {len(data_to_modify)}")

            return pd.concat([data_to_keep, data_to_modify], ignore_index=True)

    if log_file:
        _logger.info("No data has to be modified")
    return data_to_keep


def street_number_duplicator(
    data: pd.DataFrame, street_column: str, house_number_column: str, duplication_id: str = "duplication_id"
) -> pd.DataFrame:
    """Detect and replicate records where street name ends with a number and there's a separate house number.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing address information.
    street_column : str
        Column name that points to the street name.
    house_number_column : str
        Column name that points to the house number.
    duplication_id : str, optional
        Column name for duplication identifier. Default is "duplication_id".

    Returns
    -------
    pd.DataFrame
        DataFrame with records replicated based on street number + house number pattern.

    Details
    -------
    When street name ends with a number (e.g., "Debicka 3") and there's also a separate
    house number (e.g., "4"), this function creates two records:
    - One with street="Debicka", house_number="3"
    - One with street="Debicka", house_number="4"

    This handles cases where addresses like "Debicka 3" with number "4" actually represent
    two separate buildings: Debicka 3 and Debicka 4.
    """
    df = data.copy()

    if duplication_id not in df.columns:
        df[duplication_id] = pd.NA

    protected_lower = [x.lower() for x in PROTECTED_STREET_NAMES_WITH_NUMBERS]

    street_ends_with_number = df[street_column].str.match(r"^.*\s+\d+$", na=False)
    mask_not_protected = ~df[street_column].str.lower().isin(protected_lower)
    street_ends_with_number = street_ends_with_number & mask_not_protected

    # Only process rows where:
    # 1. Street ends with a number
    # 2. House number column has a value (not empty/NaN)
    has_house_number = df[house_number_column].notna() & (df[house_number_column].astype(str).str.strip() != "")

    # Extract trailing number from street
    trailing_numbers = df[street_column].str.extract(r"(\d+)$")[0]

    # Filter to only rows that need duplication
    to_duplicate = street_ends_with_number & has_house_number & trailing_numbers.notna()

    if not to_duplicate.any():
        return df

    # Get indices of records to duplicate
    duplicate_indices = df[to_duplicate].index.tolist()

    if len(duplicate_indices) == 0:
        return df

    # Build new records
    new_records = []
    for i, idx in enumerate(duplicate_indices):
        row = df.loc[idx].copy()
        street_val = str(row[street_column])
        house_num = str(row[house_number_column]).strip()
        trailing_match = re.search(r"(\d+)$", street_val)

        if trailing_match and house_num:
            trailing_num = trailing_match.group(1)
            # Get the base street name (without trailing number)
            base_street = re.sub(r"\s+\d+$", "", street_val).strip()

            # Create first record: use trailing number from street as house number
            row1 = row.copy()
            row1[street_column] = base_street
            row1[house_number_column] = trailing_num
            row1[duplication_id] = f"street_num_{i + 1}"
            new_records.append(row1)

            # Create second record: use the separate house number
            row2 = row.copy()
            row2[street_column] = base_street
            row2[house_number_column] = house_num
            row2[duplication_id] = f"street_num_{i + 1}"
            new_records.append(row2)

    # Remove original records that were duplicated
    df_result = df[~to_duplicate].copy()

    # Add new duplicated records
    if new_records:
        new_df = pd.DataFrame(new_records)
        df_result = pd.concat([df_result, new_df], ignore_index=True)

    return df_result


def clean_street_name(
    data: pd.DataFrame,
    street_column: str,
    house_number_column: str | None = None,
    bdot_var: Iterable[str] | None = None,
    log_file: bool = False,
) -> pd.DataFrame:
    """Clean street name from slasher pattern.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information, which need cleaning.
    street_column : str
        Column name that points to the street name.
    house_number_column : str
        Column name that points to the number in address.
    bdot_var : Iterable[str]
        Vector which contain street's with number in its name.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame.

    Details
    -------
    Check if street's name, which contain numbers in data is not in bdot_var. If is, than
    do nothing. If isn't than number is moved to property_number_var column if there is no value.
    Only numbers in the end of string are examined. Also it need be to be sequence of
    numbers - in the end of string must be numbers.
    """
    df = data.copy()
    # Remove abbreviations like ul., pl., os., ulica from street names
    # Remove Polish number suffixes from street names
    # Remove content in brackets from street names
    pattern_to_clean = (
        StreetPatterns.POLISH_NUMBER_SUFFIXES,
        StreetPatterns.BRACKET_CONTENT,
        StreetPatterns.ABBREVIATIONS,
        StreetPatterns.LEADING_WHITESPACE,
    )
    if street_column in df.columns:
        for pattern in pattern_to_clean:
            df[street_column] = df[street_column].str.replace(pattern, "", regex=True).str.strip()

    if house_number_column is not None and house_number_column in df.columns:
        bdot_var_lower = [str(x).lower() for x in bdot_var]
        protected_lower = [x.lower() for x in PROTECTED_STREET_NAMES_WITH_NUMBERS]
        all_protected = set(bdot_var_lower + protected_lower)

        mask_street_ends_with_number = df[street_column].str.match(StreetPatterns.ENDS_WITH_NUMBER, na=False)
        mask_not_protected = ~df[street_column].str.lower().isin(all_protected)
        mask = mask_street_ends_with_number & mask_not_protected

        # Extract trailing number-like block and move it to house_number_column if empty
        suffix = df[street_column].str.extract(f"({StreetPatterns.TRAILING_NUMBER_BLOCK})")[0]
        cond_move = mask & df[house_number_column].isna() & suffix.notna()

        # Assign extracted numbers and trim street values
        # Only remove trailing number from street when we're moving it to house_number_column
        # (i.e., when house_number_column is empty). Records where street ends with a number
        # but house_number_column already has a value will be handled by street_number_duplicator.
        df.loc[cond_move, house_number_column] = suffix[cond_move].str.strip()
        df.loc[cond_move, street_column] = df.loc[cond_move, street_column].str.replace(
            StreetPatterns.TRAILING_NUMBER_BLOCK, "", regex=True
        )

        if log_file:
            _logger.info(
                f"Moved trailing number blocks to {house_number_column} and trimmed street name for {mask.sum()} rows"
            )

    return df


def oficyna_remover(data: pd.DataFrame, house_number_column: str, deklaracja: str) -> pd.DataFrame:
    """Remove oficyna string from address number and change type of declaration.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information, which need cleaning.
    house_number_column : str
        Column name that points to the number in address.
    deklaracja : str
        Column name that points to the declaration type.

    Returns
    -------
    pd.DataFrame
        DataFrame with oficyna removed and declaration type updated.

    Details
    -------
    Oficyna usually is special part of residential building intended for commercial
    activities, thus it should be B type of declaration.
    """
    df = data.copy()

    # Change declaration type to "B" for oficyna cases
    oficyna_mask = df[house_number_column].str.contains("oficyna", case=False, na=False)
    df.loc[oficyna_mask, deklaracja] = "B"

    # Remove oficyna and everything after it
    df[house_number_column] = (
        df[house_number_column].str.replace(HouseNumberPatterns.OFICINA_BLOCK, "", case=False, regex=True).str.strip()
    )

    # Remove trailing dash if present (e.g., "4-oficyna" -> "4-" -> "4")
    df[house_number_column] = df[house_number_column].str.replace(HouseNumberPatterns.TRAILING_DASH, "", regex=True)

    return df


def dzialka_remover(data: pd.DataFrame, house_number_column: str, log_file: bool = False) -> pd.DataFrame:
    """Remove records related to ROD/działka.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information, which need cleaning.
    house_number_column : str
        Column name that points to the number in address.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with ROD/działka related records removed.

    Details
    -------
    Those observations are removed due mostly to problematic merging with building data.
    """
    df = data.copy()

    if log_file:
        _logger.info("Starting dzialka_remover")

    # Pattern to match działka/ROD related entries
    to_remove = df[house_number_column].str.contains(HouseNumberPatterns.ROD_DZIALKA, case=False, na=False)

    df = df[~to_remove].reset_index(drop=True)

    if log_file:
        _logger.info(f"Number of removed records, which contains expressions related to działka: {to_remove.sum()}")

    return df


def filter_records_with_number(data: pd.DataFrame, house_number_column: str, log_file: bool = False) -> pd.DataFrame:
    """Remove records which don't have numbers in address number.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information, which need cleaning.
    house_number_column : str
        Column name that points to the number in address.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with records that don't have numbers removed.

    Details
    -------
    In future there are needed small correction for checking if some address doesn't
    have numbers in address number.
    """
    df = data.copy()

    if log_file:
        _logger.info("Starting with_number case")

    to_remove = ~df[house_number_column].str.contains(HouseNumberPatterns.NO_NUMBER, na=False)
    df = df[~to_remove].reset_index(drop=True)

    if log_file:
        _logger.info(f"Number of removed records, which don't have number in {house_number_column}: {to_remove.sum()}")
        _logger.info("Records with no number in address number removed")

    return df


def remove_records_with_excessive_letters(
    data: pd.DataFrame, house_number_column: str, log_file: bool = False
) -> pd.DataFrame:
    """Remove strings which contain 3 or more letters in address number.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information, which need cleaning.
    house_number_column : str
        Column name that points to the number in address.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with records containing 3 or more letters removed.

    Notes
    -----
    Warning is printed if number of removed records exceeds
    EXCESSIVE_LETTERS_WARNING_THRESHOLD.
    """
    df = data.copy()

    if log_file:
        _logger.info("Starting records_too_many_letter")

    to_remove = df[house_number_column].str.contains(HouseNumberPatterns.TOO_MANY_LETTERS, na=False)

    if to_remove.sum() > EXCESSIVE_LETTERS_WARNING_THRESHOLD:
        _logger.info(
            f"Warning: There is above {EXCESSIVE_LETTERS_WARNING_THRESHOLD} removed records "
            f"due to too many letters in number variable"
        )

    if log_file:
        _logger.info(
            f"Number of deleted record, which contains 3 or more letters in {house_number_column}: {to_remove.sum()}"
        )

    return df[~to_remove].reset_index(drop=True)


def normalize_slash_pattern(
    data: pd.DataFrame,
    house_number_column: str,
    apartment_number_column: str,
    bdot_slash_patterns: Iterable[str],
    log_file: bool = False,
) -> pd.DataFrame:
    """Remove slash and numbers after it, if it isn't present in bdot_slash_patterns.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information, which need cleaning.
    house_number_column : str
        Column name that points to the address number.
    apartment_number_column : str
        Column name that points to the apartment number.
    bdot_slash_patterns : Iterable[str]
        Vector which contains address numbers that contain slash in their name from address data.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with slash patterns processed.

    Notes
    -----
    These cases are based on assumptions, that string after slash are flat number's
    in multifamily house or just wrong number and that part should go to flat_number_var
    if it is empty. In both case (empty/no-empty) symbols after slash are removed,
    if isn't present in bdot_slash_patterns.
    """
    df = data.copy()

    if log_file:
        _logger.info("Starting slash_pattern processing")

    # Check for slash pattern and not in bdot_slash_patterns
    state_to_modify = df[house_number_column].str.contains(SlashPatterns.IN_NUMBER, na=False) & ~df[
        house_number_column
    ].isin(bdot_slash_patterns)

    if log_file:
        _logger.info(f"Number of modified records is: {state_to_modify.sum()}")

    # Extract part after slash to apartment number if empty
    extracted_after_slash = df[house_number_column].str.extract(SlashPatterns.SUFFIX_CAPTURE)[0]
    cond_assign_apartment = state_to_modify & df[apartment_number_column].isna() & extracted_after_slash.notna()
    df.loc[cond_assign_apartment, apartment_number_column] = extracted_after_slash[cond_assign_apartment]

    # Remove slash and everything after it
    df.loc[state_to_modify, house_number_column] = df.loc[state_to_modify, house_number_column].str.replace(
        SlashPatterns.AND_AFTER, "", regex=True
    )

    return df


def dash_duplicator(prob_mixed: pd.DataFrame, var_number: str) -> tuple[pd.DataFrame, bool]:
    """Detection and replication based on dash pattern.

    Parameters
    ----------
    prob_mixed : pd.DataFrame
        DataFrame containing address information.
    var_number : str
        Column name that points to the address number.

    Returns
    -------
    Tuple[pd.DataFrame, bool]
        Tuple containing the processed DataFrame and a boolean indicating if pattern was invalid.

    Details
    -------
    Function detect pattern of dash in var_number. If pattern is unknown than that
    record is removed. Overall it checks what symbol is in left and right hand and
    than creates natural ordered sequence. Function assumption is that only last symbol is
    changeable. It works with numbers and letters.
    """
    numer_val = str(prob_mixed[var_number].iloc[0])
    last_symbol = numer_val[-1]

    if last_symbol.isdigit():
        dec_x = "number"
    else:
        dec_x = "letter"

    # Define patterns based on dec_x
    if dec_x == "number":
        left_hand = re.search(DashPatterns.NUMBER_BEFORE_DASH, numer_val)
        right_hand = re.search(DashPatterns.NUMBER_AFTER_DASH, numer_val)
    else:
        left_hand = re.search(DashPatterns.LETTERS_BEFORE_DASH, numer_val)
        right_hand = re.search(DashPatterns.LETTERS_AFTER_DASH, numer_val)
        base_string = re.search(ExtractionPatterns.BASE_NUMBER, numer_val)

    # Check if pattern is invalid - extract first segment before dash
    if not right_hand or (not left_hand and dec_x == "number"):
        first_part = numer_val.split("-")[0].strip()
        result_df = prob_mixed.copy()
        result_df[var_number] = first_part
        return result_df, True

    # For letter case with no left letter but has right letter (e.g., "2-2c"),
    # this means the range starts from the base number with no letter suffix
    # and goes to the base number with the right letter suffix
    # e.g., "2-2c" -> "2", "2a", "2b", "2c"
    # Only allow single letter suffixes (e.g., "2-2c" is valid, but "2-2ab" is not)
    if dec_x == "letter" and not left_hand:
        base_prefix = base_string.group() if base_string else ""
        right_str = right_hand.group(1)

        # Only allow single letter suffix
        if len(right_str) > 1:
            first_part = numer_val.split("-")[0].strip()
            result_df = prob_mixed.copy()
            result_df[var_number] = first_part
            return result_df, True

        right_position = string.ascii_lowercase.find(right_str[-1].lower()) + 1

        if right_position < 1:
            first_part = numer_val.split("-")[0].strip()
            result_df = prob_mixed.copy()
            result_df[var_number] = first_part
            return result_df, True

        # Generate: base (no letter), base+a, base+b, ..., base+right_letter
        # letter_var from 1 to right_position (1 means 'a', 2 means 'b', etc.)
        letter_var = list(range(1, right_position + 1))

        if right_str[-1].isupper():
            x = [base_prefix] + [base_prefix + string.ascii_uppercase[i - 1] for i in letter_var]
        else:
            x = [base_prefix] + [base_prefix + string.ascii_lowercase[i - 1] for i in letter_var]

        new_df = prob_mixed.iloc[[0] * len(x)].copy()
        new_df[var_number] = x
        return new_df, False

    if dec_x == "number":
        left_val = int(left_hand.group(1))
        right_val = int(right_hand.group(1))

        if left_val > right_val:
            first_part = numer_val.split("-")[0].strip()
            result_df = prob_mixed.copy()
            result_df[var_number] = first_part
            return result_df, True
        else:
            property_number_var = list(range(left_val, right_val + 1))
            new_df = prob_mixed.iloc[[0] * len(property_number_var)].copy()
            new_df[var_number] = property_number_var
            return new_df, False
    else:
        # Letter case
        left_length = len(left_hand.group(1)) if left_hand else None
        right_length = len(right_hand.group(1)) if right_hand else None

        # Both sides must have letters to form a valid range
        if left_length is not None and left_length != right_length and left_length >= 1:
            first_part = numer_val.split("-")[0].strip()
            result_df = prob_mixed.copy()
            result_df[var_number] = first_part
            return result_df, True

        if left_hand:
            left_str = left_hand.group(1)
            left_position = string.ascii_lowercase.find(left_str[-1].lower()) + 1
            # Get the base prefix (e.g., "12" from "12ab")
            base_prefix = base_string.group() if base_string else ""
        else:
            left_position = 1
            base_prefix = base_string.group() if base_string else ""
            left_str = right_hand.group(1)

        right_str = right_hand.group(1)
        right_position = string.ascii_lowercase.find(right_str[-1].lower()) + 1

        if left_position > right_position:
            first_part = numer_val.split("-")[0].strip()
            result_df = prob_mixed.copy()
            result_df[var_number] = first_part
            return result_df, True

        letter_var = list(range(left_position, right_position + 1))

        if left_str[-1].isupper():
            x = [left_str[:-1] + string.ascii_uppercase[i - 1] for i in letter_var]
        else:
            x = [left_str[:-1] + string.ascii_lowercase[i - 1] for i in letter_var]

        # Prepend base prefix if it exists (e.g., "12" from "12ab" -> "12ab", "12ac", "12ad")
        if base_prefix:
            x = [base_prefix + item for item in x]

        new_df = prob_mixed.iloc[[0] * len(x)].copy()
        new_df[var_number] = x
        return new_df, False


def duplicated_by_dash(
    data: pd.DataFrame,
    property_number_var: str,
    bdot_dash: Iterable[str],
    duplication_id: str,
    log_file: bool = False,
) -> pd.DataFrame:
    """Replicate record based on pattern of dash in property_number_var.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information.
    property_number_var : str
        Column name that points to the address number.
    bdot_dash : Iterable[str]
        Address number with dash from address data.
    duplication_id : str
        Column name for duplication identifier.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with records replicated based on dash pattern.

    Details
    -------
    Function detect records, which should be call with dash_duplicator
    function by safely map. Some string can have unknown pattern, e.g. 15a-12, and than
    are removed.
    """
    df = data.copy()

    if log_file:
        _logger.info("Starting duplicated_by_dash")

    # Detect records to modify
    state_to_modify = df[property_number_var].str.match(DashPatterns.SINGLE_DASH_RANGE, na=False) & ~df[
        property_number_var
    ].isin(bdot_dash)

    data_to_modify = df[state_to_modify].copy()
    data_to_keep = df[~state_to_modify].copy()
    rows_to_mod = len(data_to_modify)

    if rows_to_mod > 0:
        repaired_data = []
        rewizja_ceeb = []

        for idx, row in data_to_modify.iterrows():
            try:
                result_df, review = dash_duplicator(pd.DataFrame([row]), property_number_var)
                if review:
                    rewizja_ceeb.append(result_df)
                else:
                    repaired_data.append(result_df)
            except AddressParsingError as e:
                if log_file:
                    _logger.info(f"Error processing row {idx}: {e}")
                rewizja_ceeb.append(pd.DataFrame([row]))

        # Concatenate all data: kept as-is, repaired (expanded), and review (invalid patterns kept as-is)
        result_parts = [data_to_keep]

        if repaired_data:
            # Add duplication_id to repaired data
            for i, df_part in enumerate(repaired_data):
                df_part[duplication_id] = f"dash_{i + 1}"
            repaired_df = pd.concat(repaired_data, ignore_index=True)
            result_parts.append(repaired_df)

        if rewizja_ceeb:
            # Keep rows with invalid patterns as-is (don't discard them)
            rewizja_df = pd.concat(rewizja_ceeb, ignore_index=True)
            result_parts.append(rewizja_df)

        if log_file:
            _logger.info(f"Number of observation to modified: {rows_to_mod}")
            if repaired_data:
                _logger.info(f"Number of observation after replication: {len(repaired_df)}")
            if rewizja_ceeb:
                _logger.info(f"Number of observations with invalid patterns kept as-is: {len(rewizja_ceeb)}")

        return pd.concat(result_parts, ignore_index=True)
    else:
        if log_file:
            _logger.info("No data has to be modified")
        return data_to_keep


def comma_duplicator(data: pd.DataFrame, property_number_var: str) -> pd.DataFrame:
    """Detection and replication based on comma pattern.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing address information.
    property_number_var : str
        Column name that points to the address number.

    Returns
    -------
    pd.DataFrame
        DataFrame with records replicated based on comma pattern.

    Notes
    -----
    Function detects a comma-separated pattern in the number column and creates
    a sequence by splitting on comma.
    """
    numer_val = str(data[property_number_var].iloc[0])

    # Check if pattern is like "123a, b" (number followed by letters separated by comma)
    if re.search(ExtractionPatterns.COMMA_NUMBER_LETTERS, numer_val):
        number_to_add = re.search(ExtractionPatterns.LEADING_NUMBER, numer_val).group(1)
        new_numbers = numer_val.split(",")
        new_numbers = [new_numbers[0]] + [number_to_add + n.strip() for n in new_numbers[1:]]
    else:
        new_numbers = [n.strip() for n in numer_val.split(",")]

    new_df = data.iloc[[0] * len(new_numbers)].copy()
    new_df[property_number_var] = new_numbers
    return new_df


def duplicated_by_comma(
    data: pd.DataFrame, property_number_var: str, duplication_id: str, log_file: bool = False
) -> pd.DataFrame:
    """Replicate record based on comma pattern in property_number_var.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information.
    property_number_var : str
        Column name that points to the address number.
    duplication_id : str
        Column name for duplication identifier.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with records replicated based on comma pattern.

    Details
    -------
    Detects records which should be processed with comma-based replication.
    """
    return _generic_duplicator(
        data=data,
        property_number_var=property_number_var,
        pattern=r",",
        processor_fn=comma_duplicator,
        duplication_id=duplication_id,
        id_prefix="comma",
        log_file=log_file,
    )


def and_duplicator(data: pd.DataFrame, property_number_var: str) -> pd.DataFrame:
    """Detection and replication based on 'i' and 'oraz' pattern.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing address information.
    property_number_var : str
        Column name that points to the address number.

    Returns
    -------
    pd.DataFrame
        DataFrame with records replicated based on 'i' or 'oraz' pattern.

    Details
    -------
    Function detect pattern of 'i' or 'oraz' in var_number. It creates new sequence based
    on splitting symbols in var_number by 'i' or 'oraz' symbol.
    """
    numer_val = str(data[property_number_var].iloc[0])
    # Handle both " i " and " oraz " (Polish for "and")
    if " oraz " in numer_val:
        new_numbers = [n.strip() for n in numer_val.split(" oraz ")]
    else:
        new_numbers = [n.strip() for n in numer_val.split(" i ")]

    new_df = data.iloc[[0] * len(new_numbers)].copy()

    # Check if all or none have numbers
    has_numbers = [bool(re.search(ExtractionPatterns.BASE_NUMBER, n)) for n in new_numbers]

    if not (all(has_numbers) or not any(has_numbers)):
        # Some have numbers, some don't - add number from first to others
        first_number = re.search(ExtractionPatterns.BASE_NUMBER, new_numbers[0])
        if first_number:
            for i in range(1, len(new_numbers)):
                if not has_numbers[i]:
                    new_numbers[i] = first_number.group() + new_numbers[i]

    new_df[property_number_var] = new_numbers
    return new_df


def duplicated_by_and(
    data: pd.DataFrame, property_number_var: str, duplication_id: str, log_file: bool = False
) -> pd.DataFrame:
    """Replicate record based on pattern in property_number_var.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contain address information.
    property_number_var : str
        Column name that points to the address number.
    duplication_id : str
        Column name for duplication identifier.
    log_file : bool, optional
        Should be printed in logs more information. Default is False.

    Returns
    -------
    pd.DataFrame
        DataFrame with records replicated based on 'i' pattern.

    Details
    -------
    Function detect records, which should be call with and_duplicator
    function by safely map.
    """
    return _generic_duplicator(
        data=data,
        property_number_var=property_number_var,
        pattern=ExtractionPatterns.I_ORAZ,
        processor_fn=and_duplicator,
        duplication_id=duplication_id,
        id_prefix="and",
        log_file=log_file,
    )


def mieszkania_modification(
    data: pd.DataFrame,
    duplication_id: str,
    living_indicator: str,
    declaration_type: str,
    var_div2: str,
    var_div1: str,
) -> pd.DataFrame:
    """Variable modification based on frequency.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing address information.
    duplication_id : str
        Column name that points that record came from same record before replication.
    living_indicator : str
        Value of declaration_type which indicates living building.
    declaration_type : str
        Column name that points to declaration type.
    var_div2 : str
        Column name which should be decreased.
    var_div1 : str
        Column name which should be decreased.

    Returns
    -------
    pd.DataFrame
        DataFrame with values modified based on frequency.

    Details
    -------
    Function is responsible for changing values in var_div1 and var_div2. Values in these
    columns are divides by number of replication. Only modifies the specified columns
    and leaves other columns (like address numbers) unchanged.
    """
    df = data.copy()

    # Filter records to modify
    state_to_modify = df[duplication_id].notna() & df[declaration_type].isin(living_indicator)

    data_to_modify = df[state_to_modify].copy()
    data_to_keep = df[~state_to_modify].copy()

    if len(data_to_modify) > 0:
        # Count frequency of each duplication_id
        divider = data_to_modify[duplication_id].value_counts().reset_index()
        divider.columns = [duplication_id, "Freq"]

        # Merge frequency back to data
        data_to_modify = data_to_modify.merge(divider, on=duplication_id, how="left")

        # Only divide the specified columns, leave other columns unchanged
        if var_div2 in data_to_modify.columns:
            data_to_modify[var_div2] = np.floor(data_to_modify[var_div2] / data_to_modify["Freq"])
            # Set minimum value to 1 if not zero
            data_to_modify[var_div2] = np.where(
                (data_to_modify[var_div2] == 0) & data_to_modify[var_div2].notna(),
                1,
                data_to_modify[var_div2],
            )

        if var_div1 in data_to_modify.columns:
            data_to_modify[var_div1] = np.floor(data_to_modify[var_div1] / data_to_modify["Freq"])
            # Set minimum value to 1 if not zero
            data_to_modify[var_div1] = np.where(
                (data_to_modify[var_div1] == 0) & data_to_modify[var_div1].notna(),
                1,
                data_to_modify[var_div1],
            )

        # Remove frequency column
        data_to_modify = data_to_modify.drop("Freq", axis=1)

        return pd.concat([data_to_keep, data_to_modify], ignore_index=True)

    return df


def clean_house_number(data: pd.DataFrame, house_number_column: str) -> pd.DataFrame:
    """Clean house number column with all regex replacements in minimal passes.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame which contains address information.
    house_number_column : str
        Column name that points to the house number.

    Returns
    -------
    pd.DataFrame
        DataFrame with cleaned house number column.
    """
    df = data.copy()
    if house_number_column not in df.columns:
        return df

    col = df[house_number_column]

    col = col.str.replace(HouseNumberPatterns.PAREN_CONTENT, "", regex=True)
    col = col.str.replace(HouseNumberPatterns.REDUNDANT_INFO, "", case=False, regex=True)
    col = col.str.replace(HouseNumberPatterns.NUMBER_DASH_DESCRIPTION, r"\1", regex=True)
    col = col.str.strip()

    df[house_number_column] = col
    return df


class AddressCleaner:
    """Class to clean addresses using the full pipeline of cleaning functions.

    This class provides a comprehensive address cleaning pipeline that applies
    multiple cleaning functions in sequence to standardize and clean address data.

    Parameters
    ----------
    data : pd.DataFrame
        Input DataFrame containing address information to be cleaned.
    bdot_params : BdotParams
        Parameters related to BDOT data.
    ceeb_params : CeebParams
        Parameters related to CEEB data.
    flags_list : Dict[str, List[str]]
        Dictionary containing lists of known valid patterns for different address
        components.
    duplication_id : str, optional
        Column name for duplication identifier. Default is "duplication_id".
    log_file : bool, optional
        Whether to print detailed logging information. Default is False.

    Attributes
    ----------
    df : pd.DataFrame
        The DataFrame being processed.
    street_name_var : str
        Street column name.
    property_number_var : str
        Address number column name.
    flat_number_var : str
        Apartment number column name.
    deklaracja : str
        Declaration type column name.
    flags_list : Dict[str, List[str]]
        Valid patterns dictionary.
    duplication_id : str
        Duplication identifier column name.
    living_indicator : Iterable[str]
        Living building indicators.
    declaration_type : str
        Building type column name.
    var_div2 : str
        Second variable to divide column name.
    var_div1 : str
        First variable to divide column name.
    log_file : bool
        Logging flag.
    """

    def __init__(
        self,
        data: pd.DataFrame,
        bdot_params: BdotParams,
        ceeb_params: CeebParams,
        flags_list: dict[str, list[str]],
        duplication_id: str = "duplication_id",
        log_file: bool = False,
    ):
        self.df = data.copy()
        self.street_name_var = bdot_params.bdot_street_col
        self.property_number_var = bdot_params.bdot_number_col
        self.flat_number_var = ceeb_params.ceeb_lokal_col
        self.deklaracja = ceeb_params.ceeb_declare_col
        self.flags_list = flags_list
        self.duplication_id = duplication_id
        self.living_indicator = ceeb_params.ceeb_living
        self.declaration_type = ceeb_params.ceeb_declare_col
        self.var_div2 = ceeb_params.ceeb_nmb_col
        self.var_div1 = ceeb_params.ceeb_eksp_col
        self.log_file = log_file

    def clean(self) -> pd.DataFrame:
        """Execute the full address cleaning pipeline.

        This method applies a sequence of cleaning functions to standardize
        and clean address data according to the configured parameters.

        Returns
        -------
        pd.DataFrame
            Cleaned DataFrame with processed address information.

        Details
        -------
        The cleaning pipeline includes:
        - Street name cleaning
        - Oficyna removal and declaration type updates
        - ROD/działka record removal
        - Parentheses removal
        - Records without numbers removal
        - 'i' pattern duplication
        - Redundant information removal
        - Records with too many letters removal
        - Space normalization
        - Slasher pattern processing
        - Space removal and pattern normalization
        - Comma pattern duplication
        - Dash pattern duplication
        - Variable modification based on frequency
        """
        df = self.df
        df = clean_street_name(
            df,
            self.street_name_var,
            self.property_number_var,
            self.flags_list.get("street_with_number", []),
            log_file=self.log_file,
        )
        # Handle case where street ends with number and there's separate house number
        # e.g., ulica="Debicka 3" and numer_porzadkowy="4" -> two records: "Debicka 3" and "Debicka 4"
        df = street_number_duplicator(df, self.street_name_var, self.property_number_var, self.duplication_id)
        df = oficyna_remover(df, self.property_number_var, self.deklaracja)
        df = dzialka_remover(df, self.property_number_var, log_file=self.log_file)
        df = filter_records_with_number(df, self.property_number_var, log_file=self.log_file)
        df = duplicated_by_and(
            df,
            self.property_number_var,
            self.duplication_id,
            log_file=self.log_file,
        )
        df = clean_house_number(df, self.property_number_var)
        df = remove_records_with_excessive_letters(df, self.property_number_var, log_file=self.log_file)
        if self.property_number_var in df.columns:
            df[self.property_number_var] = df[self.property_number_var].str.replace(" ", "", regex=False)
        df = normalize_slash_pattern(
            df,
            self.property_number_var,
            self.flat_number_var,
            self.flags_list.get("slash_patterns", []),
            log_file=self.log_file,
        )
        if self.property_number_var in df.columns:
            df[self.property_number_var] = df[self.property_number_var].str.replace(
                HouseNumberPatterns.PUNCT_TO_REMOVE, "", regex=True
            )
        df = duplicated_by_comma(
            df,
            self.property_number_var,
            self.duplication_id,
            log_file=self.log_file,
        )
        df = duplicated_by_dash(
            df,
            self.property_number_var,
            self.flags_list.get("numer_with_dash", []),
            self.duplication_id,
            log_file=self.log_file,
        )
        df = mieszkania_modification(
            df,
            self.duplication_id,
            self.living_indicator,
            self.declaration_type,
            self.var_div2,
            self.var_div1,
        )
        return df


__all__ = [
    "clean_street_name",
    "street_number_duplicator",
    "oficyna_remover",
    "dzialka_remover",
    "filter_records_with_number",
    "duplicated_by_and",
    "clean_house_number",
    "remove_records_with_excessive_letters",
    "normalize_slash_pattern",
    "duplicated_by_comma",
    "duplicated_by_dash",
    "mieszkania_modification",
    "AddressCleaner",
]
