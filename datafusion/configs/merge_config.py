from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from datafusion.ceeb_bdot_merger.heat_source_defaults import (
    DEFAULT_AVG_APARTMENT_AREA,
    DEFAULT_BOILER_NEW,
    DEFAULT_BOILER_OLD,
    DEFAULT_CENTRAL_HIERARCHY,
    DEFAULT_CWU_HIERARCHY,
    DEFAULT_FINAL_MAPPING,
    DEFAULT_GUS_MULTIPLICATOR,
    DEFAULT_MAX_WEIGHT,
    DEFAULT_MIN_APARTMENT_COUNT,
    DEFAULT_MIN_SOURCE_PROPORTION,
    DEFAULT_MULTIFAMILY_BUILDING_TYPE,
    DEFAULT_SINGLE_FAMILY_MAX_HEAT_SOURCES,
    DEFAULT_SOLID_FUEL_AUTO,
    DEFAULT_SOLID_FUEL_MANUAL,
    DEFAULT_SOURCE_TRANSLATION,
    DEFAULT_TRASH_THRESHOLD,
)


class CeebParams(BaseModel):
    """Represents the 'ceeb_params' section of the config."""

    ceeb_merger: list[str] = Field(default_factory=lambda: ["Typ_deklaracji", "ulica", "numer_porzadkowy"])
    ceeb_boiler: list[str] = Field(default_factory=list)
    ceeb_summary: list[str] = Field(default_factory=list)
    ceeb_living: list[str] = Field(default_factory=list)
    ceeb_non_living: list[str] = Field(default_factory=list)
    ceeb_diverge: str = "Numer_domu"
    ceeb_important_col: list[str] = Field(default_factory=list)
    ceeb_device_col: str = "Źródło_ciepła"
    ceeb_street_param: str = "Ulica"
    ceeb_number_param: str = "Numer_budynku"
    ceeb_class_col: str = "Klasa_kotła"
    ceeb_declare_col: str = "Typ_deklaracji"
    ceeb_eksp_col: str = "Liczba_eksploatowanych_źródeł_ciepła"
    ceeb_nmb_col: str = "Liczba_zainstalowanych_źródeł_ciepła"
    ceeb_lokal_col: str = "Numer_lokalu"
    ceeb_cwu: str = "C.W.U."
    ceeb_co: str = "C.O."
    ind_var: list[str] = Field(default_factory=list)


class BdotParams(BaseModel):
    """Represents the 'bdot_params' section of the config."""

    bdot_street_col: str = "ulica"
    bdot_number_col: str = "numer_porzadkowy"
    bdot_geom_var: str = "geom_wkt"
    bdot_floors: str = "liczba_kondygnacji"
    bdot_pow_uzytkow: str = "pow_uzytkowa_m2"
    bdot_obrys: str = "pow_obrysu_m2"
    bdot_detail: str = "funkcja_szczegolowa_budynku"
    bdot_heat: str = "heat_connected"
    heat_distance: str = "heat_distance"
    h3_excluded_type: list[str] = Field(default_factory=list)
    bdot_col_output: list[str] = Field(default_factory=list)
    bdot_addr_var: list[str] = Field(default_factory=list)
    bdot_addr_distance: str = "addr_distance"
    bdot_id: str = "id"
    bdot_merge_var: str = "nazwa_funkcji_ogolnej"
    bdot_binary_var: list[str] = Field(default_factory=list)
    bdot_sum_var: list[str] = Field(default_factory=list)
    living_bdot: list[str] = Field(default_factory=list)
    multifamily_bdot: list[str] = Field(default_factory=list)
    non_inventory_build: list[str] = Field(default_factory=list)


class JoiningParams(BaseModel):
    """Represents the 'joining_params' section of the config."""

    var_ceeb: str = "Rodzaj_budynku_A"
    ceeb_single: str = "Budynek jednorodzinny (w tym w zabudowie bliźniaczej i szeregowej)"
    ceeb_multi: str = "Budynek wielorodzinny"
    ceeb_other: str = "Budynek zbiorowego zamieszkania"
    single_order: list[str] = Field(default_factory=list)
    multi_order: list[str] = Field(default_factory=list)
    other_order: list[str] = Field(default_factory=list)
    nonliving_order: list[str] = Field(default_factory=list)


class HeatSourceAnalysisParams(BaseModel):
    """Represents the 'heat_source_analysis_params' section for heat analysis.

    This configuration is passed to HeatSourceAnalyzer and mirrors its
    available keyword parameters.
    """

    source_translation: dict[str, str] = Field(default_factory=lambda: DEFAULT_SOURCE_TRANSLATION.copy())
    central_hierarchy: list[str] = Field(default_factory=lambda: DEFAULT_CENTRAL_HIERARCHY.copy())
    cwu_hierarchy: list[str] = Field(default_factory=lambda: DEFAULT_CWU_HIERARCHY.copy())
    final_mapping: dict[str, str] = Field(default_factory=lambda: DEFAULT_FINAL_MAPPING.copy())
    avg_apartment_area: float = Field(
        default=DEFAULT_AVG_APARTMENT_AREA,
        gt=0,
        description="Average apartment area in m2 used for apartment count estimation.",
    )
    gus_multiplicator: float = Field(
        default=DEFAULT_GUS_MULTIPLICATOR,
        gt=0,
        description="GUS multiplicator for apartment count estimation.",
    )
    floor_area_ratio_column: str = Field(
        default="wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy",
        description="Name of floor-area-ratio column used when estimating apartments.",
    )
    min_source_proportion: float = Field(
        default=DEFAULT_MIN_SOURCE_PROPORTION,
        ge=0,
        le=1,
        description=(
            "Minimum proportion of a heat source in multi-family buildings; "
            "sources below the threshold are discarded before renormalization."
        ),
    )
    trash_threshold: float = Field(
        default=DEFAULT_TRASH_THRESHOLD,
        gt=0,
        le=1,
        description=("Threshold used when iteratively pruning low-weight heat source pairs."),
    )
    multifamily_building_type: str = Field(
        default=DEFAULT_MULTIFAMILY_BUILDING_TYPE,
        description="String identifier for multi-family buildings.",
    )
    single_family_max_heat_sources: int = Field(
        default=DEFAULT_SINGLE_FAMILY_MAX_HEAT_SOURCES,
        ge=1,
        description="Maximum number of heat sources for single-family buildings.",
    )
    min_apartment_count: int = Field(
        default=DEFAULT_MIN_APARTMENT_COUNT,
        ge=1,
        description="Minimum number of apartments per building.",
    )
    max_weight: float = Field(
        default=DEFAULT_MAX_WEIGHT,
        gt=0,
        description="Maximum weight for heat source pairs.",
    )
    solid_fuel_auto: str = Field(
        default=DEFAULT_SOLID_FUEL_AUTO,
        description="Classification string for automatic solid fuel boilers.",
    )
    solid_fuel_manual: str = Field(
        default=DEFAULT_SOLID_FUEL_MANUAL,
        description="Classification string for manual solid fuel boilers.",
    )
    boiler_new: str = Field(
        default=DEFAULT_BOILER_NEW,
        description="Classification string for new boilers (Class 5/Ekoprojekt).",
    )
    boiler_old: str = Field(
        default=DEFAULT_BOILER_OLD,
        description="Classification string for old boilers (Class 4 or below).",
    )


class MergeConfig(BaseModel):
    """
    Configuration class for the final merge runner.

    This class stores configuration parameters needed for merging
    BDOT and CEEB data results from previous processing steps.
    """

    terc: str
    output_path: Path | None = None
    mock_data_path: Path | None = None

    expanded_logs: bool = True
    h3_resolution: int = 7
    coord_system: str = "EPSG:2180"
    h3_name: str = "h3_index"
    string_method: str = "cosine"
    string_max_distance: float = 0.1
    string_param: float = 1.0
    complex_distance: float = 10.0
    trash_threshold: float = DEFAULT_TRASH_THRESHOLD
    gini_in_topsis: bool = False
    gini_lorenz: bool = False
    gini_method: str = "trapz"
    classification_method: str = "topsis"

    ceeb_params: CeebParams = Field(default_factory=CeebParams)
    bdot_params: BdotParams = Field(default_factory=BdotParams)
    joining_params: JoiningParams = Field(default_factory=JoiningParams)
    heat_source_analysis_params: HeatSourceAnalysisParams = Field(default_factory=HeatSourceAnalysisParams)

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        """Validate Params values according to rules in yml_validation.R.

        Raises ValueError with collected messages when validations fail.
        """
        errors: list[str] = []

        # h3_resolution must be an integer strictly between 5 and 10 (6..9)
        if not isinstance(self.h3_resolution, int) or not (5 < self.h3_resolution < 10):
            errors.append("h3_resolution must be integer between 6 and 9")

        # gini flags must be boolean
        if not isinstance(self.gini_in_topsis, bool):
            errors.append("gini_in_topsis must be a boolean")
        if not isinstance(self.gini_lorenz, bool):
            errors.append("gini_lorenz must be a boolean")

        # gini_method must be one of allowed
        if self.gini_method not in {"trapz", "aprox"}:
            errors.append("gini_method must be 'trapz' or 'aprox'")

        # classification_method allowed values
        if self.classification_method not in {
            "average",
            "volatility",
            "distance",
            "topsis",
        }:
            errors.append("classification_method must be one of: average, volatility, distance, topsis")

        # numeric bounds
        if not (self.complex_distance > 1):
            errors.append("complex_distance must be a number greater than 1")
        if not (0 < self.string_max_distance < 1):
            errors.append("string_max_distance must be a number between 0 and 1")

        # string method allowed values (follow R list)
        allowed_string_methods = {
            "sa",
            "lv",
            "dl",
            "hamming",
            "lcs",
            "qgram",
            "cosine",
            "jaccard",
            "jw",
            "soundex",
        }
        if self.string_method not in allowed_string_methods:
            errors.append("string_method must be one of: sa, lv, dl, hamming, lcs, qgram, cosine, jaccard, jw, soundex")

        # special-case: if using 'jw' method, require smaller max distance (<= 0.25)
        if self.string_method == "jw" and not (0 < self.string_max_distance <= 0.25):
            errors.append("for 'jw' string_method, string_max_distance must be > 0 and <= 0.25")

        if errors:
            raise ValueError("; ".join(errors))

        return self
