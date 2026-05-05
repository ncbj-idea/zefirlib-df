"""Postprocessing configuration models for DataFusion."""

from pathlib import Path

from pydantic import BaseModel


class ThresholdsSubConfig(BaseModel):
    """Sub-configuration for threshold values used in operat creation."""

    threshold_a_ratio: float = 0.03
    threshold_b_ratio: float = 0.01
    float_tol: float = 0.0


class ThresholdsConfig(BaseModel):
    """Configuration for threshold values used in operat creation."""

    thresholds: ThresholdsSubConfig = ThresholdsSubConfig()


class NormalizeConfig(BaseModel):
    """Text normalization configuration."""

    lowercase: bool = False
    columns: list[str] = []


class BuildingKindByGeneralConfig(BaseModel):
    """Building kind mapping by general function."""

    wielorodzinny: list[str] = []
    jednorodzinny: list[str] = []


class BuildingKindBySpecificConfig(BaseModel):
    """Building kind mapping by specific function."""

    handlowy: list[str] = []
    biuro: list[str] = []
    przemysł: list[str] = []
    nie_ujęte: list[str] = []


class BuildingKindConfig(BaseModel):
    """Building kind classification configuration."""

    by_general: BuildingKindByGeneralConfig = BuildingKindByGeneralConfig()
    by_specific: BuildingKindBySpecificConfig = BuildingKindBySpecificConfig()


class KamienicaRulesConfig(BaseModel):
    """Tenement house rules configuration."""

    enabled: bool = False
    monument_col: str = "zabytek"
    kamienica_col: str = "kamienica"
    apply_over: list[str] = ["jednorodzinny", "wielorodzinny"]


class SolarToElectricConfig(BaseModel):
    """Solar to electric heating conversion configuration."""

    enabled: bool = True
    centralne_value: str = "Kolektory słoneczne"
    cwu_value: str = "Kolektory słoneczne"
    replacement: str = "Ogrzewanie elektryczne"


class PrintSummariesConfig(BaseModel):
    """Print summaries configuration."""

    enabled: bool = True


class ColumnsConfig(BaseModel):
    """Column mappings for postprocessing."""

    pow_uzytkowa: str = "pow_uzytkowa_m2"
    pow_obrysu: str = "pow_obrysu_m2"
    weight: str = "weight"
    merged_id: str = "merged_id"
    street: str = "ulica"
    house_no: str = "numer_porzadkowy"
    geom_wkt: str = "geom_wkt"
    funk_ogolna: str = "nazwa_funkcji_ogolnej"
    rodzaj_budynku: str = "Rodzaj_budynku"
    centralne: str = "centralne"
    h3: str = "h3_connectivity"
    h3_estimation: str = "h3_7"
    cwu: str = "cwu"
    status: str = "status"
    inwentaryzacja_flag: str = "inwentaryzacja"
    lon: str = "longitude_centroid"
    lat: str = "latitude_centroid"
    sample_flag: str = "sample_ind"


class FiltersConfig(BaseModel):
    """Row-level filtering configuration."""

    drop_if_status_in: list[str] = ["non_join"]
    drop_if_inwentaryzacja_in: list[str] = ["nie"]
    require_non_null: list[str] = ["centralne"]


class SamplingConfig(BaseModel):
    """Sampling configuration."""

    strata_col: str = "Rodzaj_budynku"
    multiway_cols: list[str] = ["centralne", "h3_connectivity", "cwu"]
    size_by_stratum: dict[str, float] = {
        "jednorodzinny": 0.02,
        "wielorodzinny": 0.03,
        "biuro": 0.3,
        "handlowy": 0.15,
        "inny": 0.1,
    }
    size_vector: list[float] | None = None
    aux_vars: list[str] = ["longitude_centroid", "latitude_centroid"]
    cube_seed: int = 5693
    float_tol: float = 0.0
    balance_iters: int = 2000


class InventoryAssignmentConfig(BaseModel):
    """Inventory assignment configuration."""

    num_surveyors: int = 6
    label_prefix: str = "Osoba_"
    start_label: int = 1


class OutputConfig(BaseModel):
    """Output configuration."""

    add_empty_inventory_cols: list[str] = [
        "przydzial",
        "Dach",
        "Okna",
        "Wiek_budynku_p_modern",
        "Ocieplenie_ścian",
        "Uwagi",
        "Zrobione",
        "street_view",
    ]


class TaxonomyMieszkalneConfig(BaseModel):
    """Residential taxonomy configuration."""

    wielorodzinny: list[str] = []
    jednorodzinny: list[str] = []


class TaxonomyBySpecificConfig(BaseModel):
    """Non-residential taxonomy by specific function."""

    handlowy: list[str] = []
    biuro: list[str] = []
    przemysł: list[str] = []
    nie_ujęte: list[str] = []


class TaxonomyConfig(BaseModel):
    """Taxonomy configuration for building classification."""

    mieszkalne: TaxonomyMieszkalneConfig = TaxonomyMieszkalneConfig()
    by_specific: TaxonomyBySpecificConfig = TaxonomyBySpecificConfig()


class ParamsConfig(BaseModel):
    """Parameters for estimation and global values calculation."""

    inventory_type: str = "Nowa_inwentaryzacja"
    calib_area: bool = True
    calib_heat: bool = True
    calib_wiel: bool = False
    calib_gas: bool = True
    calib_wiek: bool = False
    heat_strat: str = "h3_connectivity"
    h3: str = "h3_7"
    gus_factor: float = 0.8403
    hex_size: float = 0.65
    electric_h: float = 0.95
    heat_pump: float = 3.0
    krakow_factor: float = 1.0
    pv_power: float = 0.20956
    seed_open: int = 789
    seed_term: int = 542
    seed_lass: int = 123
    seed_h3: int = 598
    seed_imputation: int = 359
    mieszkalne_r: float = 0.0
    niemieszkalne_r: float = 0.0
    mieszkalne_pv: float = 0.18
    niemieszkalne_pv: float = 0.0
    pps_method: str = "systematic"
    raking_bounds_operat_a: list[float] | None = None
    raking_bounds_termo_a: list[float] | None = None
    raking_bounds_operat_b: list[float] = [-float("inf"), float("inf")]
    raking_bounds_termo_b: list[float] = [-float("inf"), float("inf")]
    electric_heater: float = 0.98


class EstimationConfig(BaseModel):
    """Estimation configuration."""

    params: ParamsConfig = ParamsConfig()
    taxonomy: TaxonomyConfig = TaxonomyConfig()


class EELivingConfig(BaseModel):
    """Electricity living configuration for protostrefy."""

    ee_total: float = 635852000.0
    multi_area: float = 5317384.0
    single_area: float = 5499600.0
    ee_factor: float = 1.1


class EEIntensityConfig(BaseModel):
    """Electricity intensity configuration by building type."""

    inny: float = 44.62207
    biuro: float = 44.62207
    handlowy: float = 44.62207
    zabytek: float = 0.0
    kamienica: float = 0.0


class ProtostrefyConfig(BaseModel):
    """Protostrefy configuration."""

    expected_cols: list[str] = []
    new_cols: list[str] = []
    ee_living: EELivingConfig = EELivingConfig()
    ee_intensity: EEIntensityConfig = EEIntensityConfig()


class PostprocessingConfig(BaseModel):
    """Complete postprocessing configuration."""

    terc: str
    input_path: Path
    output_path: Path
    thresholds: ThresholdsSubConfig = ThresholdsSubConfig()
    normalize: NormalizeConfig = NormalizeConfig()
    tourism_functions: list[str] = []
    building_kind: BuildingKindConfig = BuildingKindConfig()
    kamienica_rules: KamienicaRulesConfig = KamienicaRulesConfig()
    solar_to_electric: SolarToElectricConfig = SolarToElectricConfig()
    print_summaries: PrintSummariesConfig = PrintSummariesConfig()
    columns: ColumnsConfig = ColumnsConfig()
    filters: FiltersConfig = FiltersConfig()
    sampling: SamplingConfig = SamplingConfig()
    inventory_assignment: InventoryAssignmentConfig = InventoryAssignmentConfig()
    output: OutputConfig = OutputConfig()
    params: ParamsConfig = ParamsConfig()
    taxonomy: TaxonomyConfig = TaxonomyConfig()
    protostrefy: ProtostrefyConfig = ProtostrefyConfig()
