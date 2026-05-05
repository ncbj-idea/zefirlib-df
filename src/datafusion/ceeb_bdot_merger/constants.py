"""Constants used across BDOT modification helpers.

Keep numeric and string constants here to avoid duplication and make
tests/behavior consistent across refactors.
"""

from __future__ import annotations

from enum import Enum, unique

# Numerical stability epsilon for division by zero prevention
EPSILON = 1e-12

# Default distance threshold for non-residential building complex merging (meters, EPSG:2180)
DEFAULT_COMPLEX_DISTANCE = 5.0

# Minimum heat distance value to avoid division by zero
MIN_HEAT_DISTANCE = 1.0

# Status constants for building records
STATUS_TO_JOIN = "to_join"
STATUS_NON_JOIN = "non_join"
STATUS_UNKNOWN = "nieznany"

# Inventory constants
INVENTORY_YES = "tak"
INVENTORY_NO = "nie"


# Classification labels for synthetic index
@unique
class ClassificationLabel(Enum):
    BAD = "bad"
    BELOW_AVERAGE = "below average"
    ABOVE_AVERAGE = "above average"
    GOOD = "good"


# Ordered labels list derived from the enum
CLASSIFICATION_LABELS = [label.value for label in ClassificationLabel]

# Convenience: labels considered as "positive" connectivity
POSITIVE_CLASSIFICATION_LABELS = [
    ClassificationLabel.ABOVE_AVERAGE.value,
    ClassificationLabel.GOOD.value,
]

# Connectivity threshold (proportion of heated area to total area)
CONNECTIVITY_THRESHOLD = 0.5

# H3 ring size for neighbor analysis
H3_NEIGHBOR_RING_SIZE = 1


class ColumnNames:
    """Column name constants used across BDOT/CEEB merging code."""

    ULICA_MOD = "ulica_mod"
    BDOT_KEY = "bdot_key"
    TEMP_KEY = "temp_key"
    ULICA_SIM = "ulica_sim"
    MERGED_ID = "merged_id"
    AL_PREFIX = "al."


__all__ = [
    "EPSILON",
    "DEFAULT_COMPLEX_DISTANCE",
    "MIN_HEAT_DISTANCE",
    "STATUS_TO_JOIN",
    "STATUS_NON_JOIN",
    "STATUS_UNKNOWN",
    "INVENTORY_YES",
    "INVENTORY_NO",
    "ClassificationLabel",
    "CLASSIFICATION_LABELS",
    "POSITIVE_CLASSIFICATION_LABELS",
    "CONNECTIVITY_THRESHOLD",
    "H3_NEIGHBOR_RING_SIZE",
    "ColumnNames",
]
