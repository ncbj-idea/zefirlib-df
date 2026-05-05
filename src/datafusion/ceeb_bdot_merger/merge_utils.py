"""Merging and inventory-related utilities for BDOT processing.

Contains functions for splitting and merging building records, spatial
clustering and final dataset assembly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import pandas as pd
from shapely.strtree import STRtree

from .constants import (
    DEFAULT_COMPLEX_DISTANCE,
    INVENTORY_NO,
    INVENTORY_YES,
    STATUS_NON_JOIN,
    STATUS_TO_JOIN,
    STATUS_UNKNOWN,
)
from .geom_utils import _merge_building_geometries_and_attributes, _safe_wkt_parse
from .helpers import _create_address_key

logger = logging.getLogger(__name__)


def _find_connected_buildings_with_spatial_index(
    geometries: pd.Series, indices: list, start_idx: int, threshold: float
) -> set:
    """Find connected buildings using STRtree spatial index (optimized O(n log n)).

    Returns set of array positions (0-indexed) connected to start building.
    """
    # Filter out None geometries and create index mappings
    valid_items = [(i, idx, geometries.loc[idx]) for i, idx in enumerate(indices) if geometries.loc[idx] is not None]

    if not valid_items:
        return set()

    geom_list = [g for _, _, g in valid_items]
    array_pos_to_idx = {i: (pos, idx) for i, (pos, idx, _) in enumerate(valid_items)}
    idx_to_array_pos = {idx: i for i, (_, idx, _) in enumerate(valid_items)}

    tree = STRtree(geom_list)

    start_array_pos = idx_to_array_pos.get(start_idx)
    if start_array_pos is None:
        logger.warning(
            f"Address building (idx={start_idx}) has invalid geometry. Using first valid geometry as fallback."
        )
        start_array_pos = 0

    visited = set()
    queue = [start_array_pos]

    while queue:
        current_pos = queue.pop(0)
        if current_pos in visited:
            continue
        visited.add(current_pos)

        current_geom = geom_list[current_pos]

        buffer = current_geom.buffer(threshold)
        candidate_geoms = tree.query(buffer)

        for candidate_geom in candidate_geoms:
            candidate_pos = None
            for pos in range(len(geom_list)):
                if geom_list[pos] is candidate_geom:
                    candidate_pos = pos
                    break

            if candidate_pos is None or candidate_pos in visited:
                continue

            dist = current_geom.distance(candidate_geom)
            if dist <= threshold:
                queue.append(candidate_pos)

    result = {array_pos_to_idx[v][0] for v in visited if v in array_pos_to_idx}
    return result


def _find_addr_type(group: pd.DataFrame, cond1: str, addr_distance: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Find address building type and divide buildings into categories.

    Returns tuple (same_type, diff_type).
    """
    row_addr = group[addr_distance].astype(float).idxmin()
    inclusion_value = group.loc[row_addr, cond1]
    same_type = group.loc[group[cond1] == inclusion_value].copy()
    diff_type = group.loc[group[cond1] != inclusion_value].copy()
    return same_type, diff_type


def divide_inw_bdot(
    data: pd.DataFrame,
    divide_var: str,
    divide_values: Iterable[str],
    col_to_keep: Iterable[str],
    ulica: str,
    numer: str,
) -> dict[str, pd.DataFrame]:
    """Divide building data based on inventory criteria.

    Returns dict with 'bdot_excluded' and 'bdot_included'.
    """
    bdot_excluded = data.loc[data[divide_var].isin(list(divide_values))].copy()
    bdot_excluded["inwentaryzacja"] = INVENTORY_NO
    bdot_excluded["status"] = STATUS_UNKNOWN
    bdot_excluded["n"] = 1
    bdot_excluded["merged_id"] = bdot_excluded["id"]

    bdot_included = data.loc[~data[divide_var].isin(list(divide_values))].copy()
    bdot_included = bdot_included[list(col_to_keep)].copy()
    bdot_included["n"] = 1

    bdot_included["bdot_key"] = _create_address_key(bdot_included[ulica], bdot_included[numer])
    bdot_excluded["bdot_key"] = _create_address_key(bdot_excluded[ulica], bdot_excluded[numer])

    return {"bdot_excluded": bdot_excluded, "bdot_included": bdot_included}


def conditional_split_building(
    data: pd.DataFrame,
    cond1: str,
    living: Iterable[str],
    geom: str,
    id: str,
    addr_distance: str,
) -> dict[str, pd.DataFrame]:
    """Divide building data into single, living and non-living partitions."""
    df = data.copy()
    df["n"] = 1
    counts = df.groupby("bdot_key").size().reset_index(name="n")
    single_keys = set(counts.loc[counts["n"] == 1, "bdot_key"])
    ready_data = df.loc[df["bdot_key"].isin(single_keys)].copy()
    data_modify = df.loc[~df["bdot_key"].isin(single_keys)].copy()

    living_data = data_modify.loc[data_modify[cond1].isin(list(living))].copy()
    non_living = data_modify.loc[~data_modify[cond1].isin(list(living))].copy()

    for sub in [living_data, non_living]:
        c = sub.groupby("bdot_key").size().reset_index(name="n")
        sk = set(c.loc[c["n"] == 1, "bdot_key"])
        ready_data = pd.concat([ready_data, sub.loc[sub["bdot_key"].isin(sk)]], ignore_index=True)
        if sub is living_data:
            living_data = sub.loc[~sub["bdot_key"].isin(sk)].copy()
        else:
            non_living = sub.loc[~sub["bdot_key"].isin(sk)].copy()

    ready_non_living_parts: list[pd.DataFrame] = []
    same_type_parts: list[pd.DataFrame] = []
    for _key, grp in non_living.groupby("bdot_key"):
        same, diff = _find_addr_type(grp, cond1=cond1, addr_distance=addr_distance)
        if not diff.empty:
            diff = diff.copy()
            diff["status"] = STATUS_NON_JOIN
            ready_non_living_parts.append(diff)
        if not same.empty:
            same_type_parts.append(same)

    ready_non_living = (
        pd.concat(ready_non_living_parts, ignore_index=True)
        if ready_non_living_parts
        else pd.DataFrame(columns=non_living.columns)
    )
    non_living_same = (
        pd.concat(same_type_parts, ignore_index=True) if same_type_parts else pd.DataFrame(columns=non_living.columns)
    )

    living_data["status"] = STATUS_TO_JOIN
    ready_data["status"] = STATUS_TO_JOIN
    ready_data = pd.concat([ready_data, ready_non_living], ignore_index=True)
    ready_data["merged_id"] = ready_data[id]
    return {
        "ready_data": ready_data,
        "non_living": non_living_same,
        "living": living_data,
    }


def merge_building(
    data: pd.DataFrame,
    merge_var: str,
    id: str,
    geom: str,
    bdot_key: str,
    addr_distance: str,
    aggr_var: Iterable[str],
    addr_var: Iterable[str],
    bin_var: Iterable[str],
    living: bool,
    complex_distance: float | None = None,
    log_file: bool = False,
) -> pd.DataFrame:
    """Merge buildings into single records.

    Uses spatial index for large groups and O(n^2) for small groups.
    """
    df = data.copy()
    df["functional_split"] = df[bdot_key].astype(str) + "_" + df[merge_var].astype(str)
    groups = {k: v.copy() for k, v in df.groupby("functional_split")}
    ready_parts = []
    to_merge_parts = []
    for _k, g in groups.items():
        if len(g) == 1:
            part = g.copy()
            part["merged_id"] = part[id]
            part.drop(columns=["functional_split"], inplace=True)
            if not living:
                part["status"] = STATUS_TO_JOIN
            ready_parts.append(part)
        else:
            to_merge_parts.append(g)

    merged_rows = []
    if living:
        for g in to_merge_parts:
            merged_rows.append(
                _merge_building_geometries_and_attributes(g, id, geom, addr_distance, addr_var, aggr_var, bin_var)
            )
    else:
        threshold = float(complex_distance or DEFAULT_COMPLEX_DISTANCE)
        spatial_index_threshold = 20

        for g in to_merge_parts:
            geoms = g[geom].apply(_safe_wkt_parse)
            idxs = list(g.index)
            addr_idx = g[addr_distance].astype(float).idxmin()

            if len(idxs) > spatial_index_threshold:
                logger.debug(f"Using spatial index for {len(idxs)} buildings (threshold={spatial_index_threshold})")
                visited = _find_connected_buildings_with_spatial_index(geoms, idxs, addr_idx, threshold)
            else:
                dist_mat = [[float("inf") for _ in idxs] for __ in idxs]
                for i, ii in enumerate(idxs):
                    gi = geoms.loc[ii]
                    if gi is None:
                        continue
                    for j, jj in enumerate(idxs):
                        if i == j:
                            continue
                        gj = geoms.loc[jj]
                        if gj is None:
                            continue
                        dist_mat[i][j] = gi.distance(gj)

                start_pos = idxs.index(addr_idx)
                visited = set()
                queue = [start_pos]
                while queue:
                    pos = queue.pop(0)
                    if pos in visited:
                        continue
                    visited.add(pos)
                    neighbors = [j for j, d in enumerate(dist_mat[pos]) if d <= threshold]
                    for nb in neighbors:
                        if nb not in visited:
                            queue.append(nb)

            complex_rows = g.loc[[idxs[i] for i in sorted(visited)]]
            non_complex_rows = g.loc[[idxs[i] for i in range(len(idxs)) if i not in visited]].copy()
            if not complex_rows.empty:
                merged_rows.append(
                    _merge_building_geometries_and_attributes(
                        complex_rows,
                        id,
                        geom,
                        addr_distance,
                        addr_var,
                        aggr_var,
                        bin_var,
                    )
                )
            if not non_complex_rows.empty:
                non_complex_rows = non_complex_rows.copy()
                non_complex_rows = non_complex_rows.drop(columns=["functional_split"])
                non_complex_rows["status"] = STATUS_NON_JOIN
                non_complex_rows["merged_id"] = non_complex_rows[id]
                ready_parts.append(non_complex_rows)

    temp_df = pd.concat(merged_rows, ignore_index=True) if merged_rows else pd.DataFrame()
    ready_df = pd.concat(ready_parts, ignore_index=True) if ready_parts else pd.DataFrame(columns=df.columns)
    out = pd.concat([temp_df, ready_df], ignore_index=True, sort=False)
    return out


def create_pyszny_bdot(
    data_ready: pd.DataFrame,
    data_living: pd.DataFrame,
    data_nonliving: pd.DataFrame,
    data_excluded: pd.DataFrame,
) -> pd.DataFrame:
    """Create final form of building data combining processed parts."""
    final_merged = pd.concat([data_ready, data_living, data_nonliving], axis=0, ignore_index=True)
    final_merged["inwentaryzacja"] = INVENTORY_YES
    excluded = data_excluded.reindex(columns=final_merged.columns, fill_value=pd.NA)
    return pd.concat([final_merged, excluded], axis=0, ignore_index=True)


__all__ = [
    "_find_connected_buildings_with_spatial_index",
    "_find_addr_type",
    "divide_inw_bdot",
    "conditional_split_building",
    "merge_building",
    "create_pyszny_bdot",
]
