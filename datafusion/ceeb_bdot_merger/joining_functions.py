from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from rapidfuzz import process

from .constants import ColumnNames
from .helpers import _create_address_key, _validate_columns_exist


def prepare_data_to_join(input_data: pd.DataFrame, street_var: str, number_var: str) -> pd.DataFrame:
    """
    Prepare data for joining procedure.

    Reduce letter size and remove spaces from address variables. In the end
    create bdot_key variable (pasted address variables).

    Parameters
    ----------
    input_data : pd.DataFrame
        Input dataframe.
    street_var : str
        Column name that points to street names.
    number_var : str
        Column name that points to address number.

    Returns
    -------
    pd.DataFrame
        DataFrame with prepared data.
    """
    # validate required input columns
    _validate_columns_exist(input_data, [street_var], context="prepare_data_to_join")

    prepared_data = input_data.copy()
    # street normalize: remove spaces, to lower, trim, replace leading 'al.' with 'aleja'
    street_values = prepared_data.get(street_var, pd.Series(["" for _ in range(len(prepared_data))]))
    street_modified = (
        street_values.astype(str)
        .str.replace(" ", "", regex=False)
        .str.lower()
        .str.replace(r"^al\.", "aleja", regex=True)
        .str.strip()
    )
    prepared_data[ColumnNames.ULICA_MOD] = street_modified
    # numer lower
    if number_var in prepared_data.columns:
        prepared_data[number_var] = prepared_data[number_var].astype(str).str.lower()
    else:
        prepared_data[number_var] = ""
    # use helper to create a predictable address key
    prepared_data[ColumnNames.BDOT_KEY] = _create_address_key(
        prepared_data[ColumnNames.ULICA_MOD], prepared_data[number_var]
    )
    return prepared_data


def deterministic_join(
    building_data: pd.DataFrame,
    ceeb_data: pd.DataFrame,
    join_key: str,
    number_var: str,
    street_var: str,
) -> dict[str, pd.DataFrame]:
    """
    Perform deterministic join by key.

    Simple inner join. Result is three dataframes: merged data, non-merged
    building data and non-merged CEEB data.

    Parameters
    ----------
    building_data : pd.DataFrame
        Building dataframe.
    ceeb_data : pd.DataFrame
        CEEB dataframe.
    join_key : str
        Key column for joining.
    number_var : str
        Column name that points to address number.
    street_var : str
        Column name that points to street names.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Dictionary with three dataframes: 'merged_data' (merged),
        'unmerged_building_data' (non-merged from building_data),
        'unmerged_ceeb_data' (non-merged from ceeb_data).

    Notes
    -----
    number_var and street_var are arguments because they have to be removed - both
    data frames have same set of columns.
    """
    # validate required columns exist in both dataframes
    _validate_columns_exist(building_data, [join_key], context="deterministic_join:building_data")
    _validate_columns_exist(ceeb_data, [join_key], context="deterministic_join:ceeb_data")

    # inner join many-to-many by key; drop duplicate address columns from right side
    columns_to_drop = [col for col in [number_var, street_var, ColumnNames.ULICA_MOD] if col in ceeb_data.columns]
    ceeb_data_for_join = ceeb_data.drop(columns=columns_to_drop, errors="ignore")

    # Handle potential ID column conflicts by renaming CEEB's ID column
    # This ensures we have a clean 'id' column in the merged data for downstream processing
    if "id" in building_data.columns and "id" in ceeb_data_for_join.columns:
        ceeb_data_for_join = ceeb_data_for_join.rename(columns={"id": "id_ceeb"})

    merged_data = building_data.merge(ceeb_data_for_join, how="inner", on=join_key)
    matched_keys_index = pd.Index(merged_data[join_key].unique()) if join_key in merged_data.columns else pd.Index([])
    unmerged_building_data = building_data.loc[~building_data[join_key].isin(matched_keys_index)].copy()
    unmerged_ceeb_data = ceeb_data.loc[~ceeb_data[join_key].isin(matched_keys_index)].copy()
    return {
        "merged_data": merged_data,
        "unmerged_building_data": unmerged_building_data,
        "unmerged_ceeb_data": unmerged_ceeb_data,
    }


def similarity_join(
    building_target_data: pd.DataFrame,
    ceeb_source_data: pd.DataFrame,
    street_similarity_var: str,
    number_var: str,
    street_var: str,
    address_key: str,
    similarity_method: str,
    max_similarity_distance: float,
    similarity_threshold: float,
) -> dict[str, pd.DataFrame]:
    """
    Merge CEEB and building data based on similarity match.

    After evaluation of dissimilarity of street names, creates bdot_key with
    new value based on matched string.

    Parameters
    ----------
    building_target_data : pd.DataFrame
        Building data.
    ceeb_source_data : pd.DataFrame
        CEEB report.
    street_similarity_var : str
        ulica_mod column.
    number_var : str
        Column name that points to address number.
    street_var : str
        Column name that points to street names.
    address_key : str
        bdot_key column.
    similarity_method : str
        Method of string matching algorithm. One of:
        "osa", "lv", "dl", "hamming", "lcs", "qgram", "cosine", "jaccard",
        "jw","soundex". The best results have been achieved with cosine so far.
    max_similarity_distance : float
        Number between 0 and 1. Describes maximum distance
        to recognize string as similar.
    similarity_threshold : float
        See arguments in stringdist::amatch.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Dictionary with three dataframes: 'merged_data' (merged),
        'unmerged_building_data' (non-merged from building_target_data),
        'unmerged_ceeb_data' (non-merged from ceeb_source_data).
    """
    # validate required columns
    _validate_columns_exist(
        building_target_data,
        [street_similarity_var, address_key],
        context="similarity_join:building_target_data",
    )
    _validate_columns_exist(
        ceeb_source_data,
        [street_similarity_var, number_var, address_key],
        context="similarity_join:ceeb_source_data",
    )
    if building_target_data.empty or ceeb_source_data.empty:
        return {
            "merged_data": pd.DataFrame(),
            "unmerged_building_data": building_target_data,
            "unmerged_ceeb_data": ceeb_source_data,
        }

    ceeb_working_data = ceeb_source_data.copy()
    # Use index to uniquely identify rows from `ceeb_source_data` for correct post-join filtering.
    ceeb_working_data["__original_index__"] = ceeb_source_data.index
    # Candidate choices are unique street values from building data
    unique_streets = pd.unique(building_target_data[street_similarity_var])

    # Deduplicate queries from CEEB to avoid repeated matching work
    unique_queries = pd.unique(ceeb_working_data[street_similarity_var])
    score_cutoff = (1 - max_similarity_distance) * 100

    matched_map = {}
    for q in unique_queries:
        if pd.isna(q):
            matched_map[q] = None
            continue
        result = process.extractOne(q, unique_streets, score_cutoff=score_cutoff)
        matched_map[q] = result[0] if result else None

    ceeb_working_data[ColumnNames.ULICA_SIM] = ceeb_working_data[street_similarity_var].map(matched_map)

    # Filter out rows where the match is the same as the original or no match was found
    ceeb_working_data = ceeb_working_data.dropna(subset=[ColumnNames.ULICA_SIM])
    ceeb_working_data = ceeb_working_data[
        ceeb_working_data[street_similarity_var] != ceeb_working_data[ColumnNames.ULICA_SIM]
    ]

    # Create the new join key based on the similarity-matched street name
    ceeb_working_data[address_key] = _create_address_key(
        ceeb_working_data[ColumnNames.ULICA_SIM], ceeb_working_data[number_var]
    )

    # Select columns to drop from the right side of the join
    columns_to_drop = [
        column for column in [number_var, street_var, ColumnNames.ULICA_MOD] if column in ceeb_working_data.columns
    ]

    # Handle potential ID column conflicts by renaming CEEB's ID column
    # This ensures we have a clean 'id' column in the merged data for downstream processing
    ceeb_working_data_clean = ceeb_working_data.drop(columns=columns_to_drop)
    if "id" in building_target_data.columns and "id" in ceeb_working_data_clean.columns:
        ceeb_working_data_clean = ceeb_working_data_clean.rename(columns={"id": "id_ceeb"})

    # Perform the inner join
    merged_data = pd.merge(
        building_target_data,
        ceeb_working_data_clean,
        on=address_key,
        how="inner",
    )

    # Determine the remaining dataframes
    merged_address_index = pd.Index(merged_data[address_key].unique()) if not merged_data.empty else pd.Index([])
    unmerged_building_data = building_target_data[~building_target_data[address_key].isin(merged_address_index)]

    # Correctly identify non-merged rows from `ceeb_source_data` using the temporary index
    if not merged_data.empty:
        merged_indices = merged_data["__original_index__"].unique()
        unmerged_ceeb_data = ceeb_source_data[~ceeb_source_data.index.isin(merged_indices)].copy()
        # Clean up the temporary index column from the final merged data
        merged_data = merged_data.drop(columns=["__original_index__"])
    else:
        # No rows were merged from `ceeb_source_data`
        unmerged_ceeb_data = ceeb_source_data.copy()

    return {
        "merged_data": merged_data,
        "unmerged_building_data": unmerged_building_data,
        "unmerged_ceeb_data": unmerged_ceeb_data,
    }


def number_remover_join(
    building_data: pd.DataFrame,
    ceeb_target_data: pd.DataFrame,
    street_mod_var: str,
    number_var: str,
    street_var: str,
    address_key: str,
) -> dict[str, pd.DataFrame]:
    """
    Remove non-number symbols from dataframe column and join.

    Parameters
    ----------
    building_data : pd.DataFrame
        Building data.
    ceeb_target_data : pd.DataFrame
        CEEB report.
    street_mod_var : str
        ulica_mod column.
    number_var : str
        Column name that points to address number.
    street_var : str
        Column name that points to street names.
    address_key : str
        bdot_key column.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Dictionary with two dataframes: 'merged_data' (result), 'unmerged_data' (missed).
    """
    # validate required columns
    _validate_columns_exist(
        building_data,
        [street_mod_var, number_var, address_key],
        context="number_remover_join:building_data",
    )
    _validate_columns_exist(ceeb_target_data, [address_key], context="number_remover_join:ceeb_target_data")

    if building_data.empty:
        return {"merged_data": pd.DataFrame(), "unmerged_data": building_data}

    # Build temp_key = lower(street) + normalized(number)
    working_data = building_data.copy()
    street_lower = working_data.get(street_mod_var, pd.Series([""] * len(working_data))).astype(str).str.lower()
    number_values = working_data.get(number_var, pd.Series([""] * len(working_data))).astype(str).str.lower()
    # Normalize the address number by removing all non-alphanumeric characters.
    # This is more robust than just extracting the first number.
    normalized_number = number_values.str.replace(r"[^a-z0-9]", "", regex=True)
    working_data[ColumnNames.TEMP_KEY] = (street_lower + normalized_number).str.replace(" ", "", regex=False)
    # Build fast membership index of target keys
    target_keys_index = pd.Index(pd.unique(ceeb_target_data.get(address_key, pd.Series(dtype=str))))
    match_flag = working_data[ColumnNames.TEMP_KEY].isin(target_keys_index)
    data_to_join = working_data.loc[match_flag].copy()
    data_to_join[address_key] = data_to_join[ColumnNames.TEMP_KEY]
    data_to_join = data_to_join.drop(columns=[ColumnNames.TEMP_KEY], errors="ignore")
    unmerged_data = working_data.loc[~match_flag].copy()
    unmerged_data = unmerged_data.drop(columns=[ColumnNames.TEMP_KEY], errors="ignore")
    # left join to bring ceeb_target_data attributes (without address duplicates)
    columns_to_drop = [
        col for col in [number_var, street_var, ColumnNames.ULICA_MOD] if col in ceeb_target_data.columns
    ]
    ceeb_data_for_join = ceeb_target_data.drop(columns=columns_to_drop, errors="ignore")

    # Handle potential ID column conflicts by renaming CEEB's ID column
    # This ensures we have a clean 'id' column in the merged data for downstream processing
    if "id" in data_to_join.columns and "id" in ceeb_data_for_join.columns:
        ceeb_data_for_join = ceeb_data_for_join.rename(columns={"id": "id_ceeb"})

    merged_data = data_to_join.merge(ceeb_data_for_join, how="left", on=address_key)
    return {"merged_data": merged_data, "unmerged_data": unmerged_data}


def alahomora(
    building_data: pd.DataFrame,
    ceeb_data: pd.DataFrame,
    street_mod_var: str,
    number_var: str,
    street_var: str,
    address_key: str,
) -> dict[str, pd.DataFrame]:
    """
    Merge CEEB and building data based on modification of address number.

    Working around address number by removing all non-number values. First procedure
    is done in CEEB data and next after non-merged data on building data.

    Parameters
    ----------
    building_data : pd.DataFrame
        Building data.
    ceeb_data : pd.DataFrame
        CEEB report.
    street_mod_var : str
        ulica_mod column.
    number_var : str
        Column name that points to address number.
    street_var : str
        Column name that points to street names.
    address_key : str
        bdot_key column.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Dictionary with three dataframes: 'merged_data' (merged),
        'unmerged_building_data' (non-merged from building_data),
        'unmerged_ceeb_data' (non-merged from ceeb_data).
    """
    # validate required columns on both sides
    _validate_columns_exist(
        building_data,
        [street_mod_var, number_var, street_var, address_key],
        context="alahomora:building_data",
    )
    _validate_columns_exist(
        ceeb_data,
        [street_mod_var, number_var, street_var, address_key],
        context="alahomora:ceeb_data",
    )

    if building_data.empty or ceeb_data.empty:
        return {
            "merged_data": pd.DataFrame(),
            "unmerged_building_data": building_data,
            "unmerged_ceeb_data": ceeb_data,
        }

    first_join = number_remover_join(
        building_data=ceeb_data,
        ceeb_target_data=building_data,
        street_mod_var=street_mod_var,
        number_var=number_var,
        street_var=street_var,
        address_key=address_key,
    )
    remaining_building_data = building_data.loc[
        ~building_data[address_key].isin(first_join["merged_data"][address_key])
    ].copy()
    second_join = number_remover_join(
        building_data=remaining_building_data,
        ceeb_target_data=first_join["unmerged_data"],
        street_mod_var=street_mod_var,
        number_var=number_var,
        street_var=street_var,
        address_key=address_key,
    )
    merged_data = pd.concat(
        [first_join["merged_data"], second_join["merged_data"]],
        axis=0,
        ignore_index=True,
    )
    remaining_ceeb_data = (
        first_join["unmerged_data"]
        .loc[~first_join["unmerged_data"][address_key].isin(second_join["merged_data"][address_key])]
        .copy()
    )
    return {
        "merged_data": merged_data,
        "unmerged_building_data": second_join["unmerged_data"],
        "unmerged_ceeb_data": remaining_ceeb_data,
    }


def magic_join(
    building_data: pd.DataFrame,
    ceeb_data: pd.DataFrame,
    address_key: str,
    street_mod_var: str,
    number_var: str,
    street_var: str,
    similarity_method: str,
    max_similarity_distance: float,
    similarity_threshold: float,
) -> dict[str, pd.DataFrame]:
    """
    Merge CEEB and building data.

    The procedure consists of four steps. First both data are prepared for joining.
    Next deterministic join is applied. Third step is merging based on similarity in
    street names (new value of bdot_key). Final step is working around address
    number. In each merging step, non-merged data from previous step is used.

    Parameters
    ----------
    building_data : pd.DataFrame
        Building data.
    ceeb_data : pd.DataFrame
        CEEB report.
    address_key : str
        bdot_key column.
    street_mod_var : str
        ulica_mod column.
    number_var : str
        Column name that points to address number.
    street_var : str
        Column name that points to street names.
    similarity_method : str
        Method of string matching algorithm. One of:
        "osa", "lv", "dl", "hamming", "lcs", "qgram", "cosine", "jaccard",
        "jw","soundex". The best results have been achieved with cosine so far.
    max_similarity_distance : float
        Number between 0 and 1. Describes maximum distance
        to recognize string as similar.
    similarity_threshold : float
        See arguments in stringdist::amatch.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Dictionary with three dataframes: 'merged_data' (merged), 'unmerged_building_data'
        (non-merged building data), 'unmerged_ceeb_data' (non-merged CEEB data).
    """
    # Prepare both sides
    ceeb_prepared = prepare_data_to_join(ceeb_data, street_var=street_var, number_var=number_var)
    building_prepared = prepare_data_to_join(building_data, street_var=street_var, number_var=number_var)

    # Step 1: deterministic join
    deterministic_result = deterministic_join(building_prepared, ceeb_prepared, address_key, number_var, street_var)

    # Step 2: similarity join on street names (rapidfuzz)
    similarity_result = similarity_join(
        building_target_data=deterministic_result["unmerged_building_data"],
        ceeb_source_data=deterministic_result["unmerged_ceeb_data"],
        street_similarity_var=street_mod_var,
        number_var=number_var,
        street_var=street_var,
        address_key=address_key,
        similarity_method=similarity_method,
        max_similarity_distance=max_similarity_distance,
        similarity_threshold=similarity_threshold,
    )

    # Step 3: numeric-based address handling
    numeric_result = alahomora(
        building_data=similarity_result["unmerged_building_data"],
        ceeb_data=similarity_result["unmerged_ceeb_data"],
        street_mod_var=street_mod_var,
        number_var=number_var,
        street_var=street_var,
        address_key=address_key,
    )

    merged_data = pd.concat(
        [
            deterministic_result["merged_data"],
            similarity_result["merged_data"],
            numeric_result["merged_data"],
        ],
        axis=0,
        ignore_index=True,
    )

    return {
        "merged_data": merged_data,
        "unmerged_building_data": numeric_result["unmerged_building_data"],
        "unmerged_ceeb_data": numeric_result["unmerged_ceeb_data"],
    }


# Correction routines (imperio and helpers) unchanged


def _filter_by_building_type(
    input_data: pd.DataFrame,
    building_type_order: Iterable[str],
    building_type_var: str,
    unique_key_var: str,
    inclusive: bool,
    ceeb_building_type_var: str | None = None,
    filter_value: str | Iterable[str] | None = None,
) -> pd.DataFrame:
    """
    Filters and orders records based on building type from CEEB and BDOT data.
    This is a generalized function to replace `special_join` and `ultra_special_join`.

    Parameters
    ----------
    input_data : pd.DataFrame
        Input dataframe.
    building_type_order : Iterable[str]
        Order of building type based on values from building_type_var.
    building_type_var : str
        Column name that points to building type in building data.
    unique_key_var : str
        The column name for the unique key used to track records.
    inclusive : bool
        If True, performs an inclusive selection (like `special_join`).
        If False, performs an exclusive selection (like `ultra_special_join`).
    ceeb_building_type_var : str, optional
        Column name that points to building type in CEEB data. Required for inclusive mode.
    filter_value : str | Iterable[str], optional
        Feature value in ceeb_building_type_var to filter by. Required for inclusive mode.

    Returns
    -------
    pd.DataFrame
        Filtered dataframe.
    """
    filtered_records = []
    if inclusive:
        if ceeb_building_type_var is None or filter_value is None:
            raise ValueError("`ceeb_building_type_var` and `filter_value` are required for inclusive mode.")
        filtered_subset = input_data.loc[
            input_data[ceeb_building_type_var].isin(
                [filter_value] if isinstance(filter_value, str) else list(filter_value)
            )
        ].copy()
        for building_type in building_type_order:
            if building_type != "others":
                current_records = filtered_subset.loc[filtered_subset[building_type_var] == building_type].copy()
            else:
                current_records = filtered_subset.copy()
            if not current_records.empty:
                filtered_records.append(current_records)
                filtered_subset = filtered_subset.loc[
                    ~filtered_subset[unique_key_var].isin(current_records[unique_key_var])
                ].copy()
            if filtered_subset.empty:
                break
    else:  # Exclusive mode
        filtered_subset = input_data.copy()
        building_order_list = [""] + list(building_type_order)
        while len(building_order_list) > 0:
            building_order_list = building_order_list[1:]
            if len(building_order_list) != 1:
                current_records = filtered_subset.loc[
                    ~filtered_subset[building_type_var].isin(building_order_list)
                ].copy()
            else:
                current_records = filtered_subset.copy()
            if not current_records.empty:
                filtered_records.append(current_records)
                filtered_subset = filtered_subset.loc[
                    ~filtered_subset[unique_key_var].isin(current_records[unique_key_var])
                ].copy()
            if filtered_subset.empty:
                break

    return (
        pd.concat(filtered_records, axis=0, ignore_index=True)
        if filtered_records
        else pd.DataFrame(columns=input_data.columns)
    )


def imperio(
    merged_input_data: pd.DataFrame,
    building_columns,
    declaration_type_var: str,
    residential_indicators,
    non_residential_indicators,
    address_key: str,
    merged_id_var: str,
    building_building_type_var: str,
    ceeb_building_type_var: str,
    ceeb_single_family_value: str,
    ceeb_collective_residence_value: str,
    ceeb_multi_family_value: str,
    ceeb_multi_family_order,
    ceeb_single_family_order,
    ceeb_collective_residence_order,
    ceeb_non_residential_order,
) -> dict[str, pd.DataFrame]:
    """
    Correction of merged data based on building type.

    Merged data was only based on address data, but in both data, there is
    information about building type. This function allows to make correction.
    Records at the same address (common bdot_key) are checked for values of
    building type in building and CEEB variable. If they share same type and
    at the address remain some building, then these building are treated as
    non-merged. If not, then it iterates to next type of building in order vector.

    Parameters
    ----------
    merged_input_data : pd.DataFrame
        Input dataframe.
    building_columns : list
        Column names in building data.
    declaration_type_var : str
        Column name that points to declaration type.
    residential_indicators : list
        Feature value in declaration_type_var, which indicate declaration
        for residential building.
    non_residential_indicators : list
        Feature value in declaration_type_var, which indicate declaration
        for non-residential building.
    address_key : str
        bdot_key column.
    merged_id_var : str
        merged_id column.
    building_building_type_var : str
        Column name that points building type in building data.
    ceeb_building_type_var : str
        Column name that points to building type in CEEB.
    ceeb_single_family_value : str
        Feature value, which describe single family house in
        CEEB data.
    ceeb_collective_residence_value : str
        Feature value, which describe collective residence building in
        CEEB data.
    ceeb_multi_family_value : str
        Feature value, which describe multi family house in
        CEEB data.
    ceeb_multi_family_order : list
        The order in which the correction is to take place for
        multi family house.
    ceeb_single_family_order : list
        The order in which the correction is to take place for
        single family house.
    ceeb_collective_residence_order : list
        Order in which the correction is to take place for
        collective building.
    ceeb_non_residential_order : list
        The order in which the correction is to take place for
        non-residential building.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Dictionary with two dataframes: 'merged_data' (corrected merged), 'non_merged_data' (non-merged).
    """
    # Split living vs non-living by declaration
    residential_data = merged_input_data.loc[
        merged_input_data[declaration_type_var].isin(list(residential_indicators))
    ].copy()
    non_residential_data = merged_input_data.loc[
        ~merged_input_data[declaration_type_var].isin(list(residential_indicators))
    ].copy()

    # Normalize CEEB building type: set to 'inny' when NA or in ceeb_collective_residence_value
    def _normalize_ceeb_building_type(series: pd.Series) -> pd.Series:
        normalized_series = series.copy()
        normalized_series = normalized_series.where(~normalized_series.isna(), other="inny")
        normalized_series = normalized_series.where(
            ~normalized_series.isin(
                [ceeb_collective_residence_value]
                if isinstance(ceeb_collective_residence_value, str)
                else list(ceeb_collective_residence_value)
            ),
            other="inny",
        )
        return normalized_series

    if ceeb_building_type_var in residential_data.columns:
        residential_data[ceeb_building_type_var] = _normalize_ceeb_building_type(
            residential_data[ceeb_building_type_var]
        )
    # Build parts
    single_family_houses = _filter_by_building_type(
        residential_data,
        building_type_order=list(ceeb_single_family_order),
        building_type_var=building_building_type_var,
        ceeb_building_type_var=ceeb_building_type_var,
        filter_value=ceeb_single_family_value,
        unique_key_var=address_key,
        inclusive=True,
    )
    multi_family_houses = _filter_by_building_type(
        residential_data,
        building_type_order=list(ceeb_multi_family_order),
        building_type_var=building_building_type_var,
        ceeb_building_type_var=ceeb_building_type_var,
        filter_value=ceeb_multi_family_value,
        unique_key_var=address_key,
        inclusive=True,
    )
    other_residential = _filter_by_building_type(
        residential_data,
        building_type_order=list(ceeb_collective_residence_order),
        building_type_var=building_building_type_var,
        ceeb_building_type_var=ceeb_building_type_var,
        filter_value="inny",
        unique_key_var=address_key,
        inclusive=True,
    )
    non_residential_buildings = _filter_by_building_type(
        input_data=non_residential_data,
        building_type_order=list(ceeb_non_residential_order),
        building_type_var=building_building_type_var,
        unique_key_var=address_key,
        inclusive=False,
    )
    corrected_merged_data = pd.concat(
        [
            single_family_houses,
            multi_family_houses,
            other_residential,
            non_residential_buildings,
        ],
        axis=0,
        ignore_index=True,
    )
    corrected_non_merged_data = merged_input_data.loc[
        ~merged_input_data[merged_id_var].isin(corrected_merged_data.get(merged_id_var, pd.Series(dtype=str)))
    ].copy()
    corrected_non_merged_data = (
        corrected_non_merged_data[list(building_columns)] if building_columns is not None else corrected_non_merged_data
    )
    return {
        "merged_data": corrected_merged_data,
        "non_merged_data": corrected_non_merged_data,
    }


__all__ = [
    "magic_join",
    "imperio",
]
