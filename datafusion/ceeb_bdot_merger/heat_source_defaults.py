"""Default configuration values and mappings for heat source analysis."""

# Default numeric constants for heat source analysis
DEFAULT_AVG_APARTMENT_AREA: float = 68.3  # Average apartment area in m2
DEFAULT_GUS_MULTIPLICATOR: float = 1.0  # GUS multiplicator for apartment count estimation
DEFAULT_MIN_SOURCE_PROPORTION: float = 0.10  # Minimum source proportion threshold for multi-family buildings
DEFAULT_TRASH_THRESHOLD: float = 0.25  # Threshold for removing low-weight heat source pairs
DEFAULT_FLOOR_AREA_RATIO: float = 1.0  # Default floor-to-footprint ratio fallback
DEFAULT_MIN_APARTMENT_COUNT: int = 1  # Minimum apartment count
DEFAULT_MAX_WEIGHT: float = 1.0  # Default max weight for heat source pairs
DEFAULT_SINGLE_FAMILY_MAX_HEAT_SOURCES: int = 1  # Max heat sources for single-family buildings

# Default building type strings
DEFAULT_MULTIFAMILY_BUILDING_TYPE: str = "Budynek wielorodzinny"  # Multi-family building type

# Default heat source classification strings
DEFAULT_SOLID_FUEL_AUTO: str = "solid_fuel_auto"  # Automatic feeder solid fuel boiler
DEFAULT_SOLID_FUEL_MANUAL: str = "solid_fuel_manual"  # Manual feeder solid fuel boiler
DEFAULT_BOILER_NEW: str = "boiler_new"  # New boiler classification
DEFAULT_BOILER_OLD: str = "boiler_old"  # Old boiler classification

# Default source translation map (ported from One_big_script.R)
DEFAULT_SOURCE_TRANSLATION: dict[str, str] = {
    "Miejska sieć ciepłownicza / ciepło systemowe / lokalna sieć ciepłownicza": "district_heating",
    "Miejska sieć ciepłownicza": "district_heating",
    "Kocioł gazowy / bojler gazowy / podgrzewacz gazowy przepływowy / kominek gazowy": "gas_boiler",
    "Kocioł gazowy": "gas_boiler",
    "Kocioł olejowy": "oil_boiler",
    "Kocioł na paliwo stałe (węgiel, drewno, pellet lub inny rodzaj biomasy) z automatycznym podawaniem paliwa / z podajnikiem": "solid_fuel_auto",  # noqa: E501
    "Kocioł na paliwo stałe - pod. automatyczne": "solid_fuel_auto",
    "Kocioł na paliwo stałe (węgiel, drewno, pellet lub inny rodzaj biomasy) z ręcznym podawaniem paliwa / zasypowy": "solid_fuel_manual",  # noqa: E501
    "Kocioł na paliwo stałe - pod. ręczne": "solid_fuel_manual",
    "Ekoprojekt": "boiler_new",
    "Klasa_5": "boiler_new",
    "Klasa_4": "boiler_old",
    "Klasa_3": "boiler_old",
    "Poniżej_klasy_3_lub_brak_informacji": "boiler_old",
    "Pompa ciepła": "heat_pump",
    "Ogrzewanie elektryczne / bojler elektryczny": "electric_heating",
    "Ogrzewanie elektryczne": "electric_heating",
    "Kolektory słoneczne do ciepłej wody użytkowej lub z funkcją wspomagania ogrzewania": "electric_heating",
    "Trzon kuchenny / piecokuchnia / kuchnia węglowa": "kitchen_stove",
    "Trzon kuchenny": "kitchen_stove",
    "Piec kaflowy na paliwo stałe (węgiel, drewno, pellet lub inny rodzaj biomasy)": "tile_stove",
    "Piec kaflowy": "tile_stove",
    "Kominek / koza / ogrzewacz powietrza na paliwo stałe (drewno, pellet lub inny rodzaj biomasy, węgiel)": "fireplace",  # noqa: E501
    "Kominek": "fireplace",
    "Inne": "other",
    "Brak informacji": "no_info",
}

# Default central heating hierarchy (ported from divice_dimension.R)
DEFAULT_CENTRAL_HIERARCHY: list[str] = [
    "district_heating",
    "boiler_new",
    "gas_boiler",
    "boiler_old",
    "oil_boiler",
    "heat_pump",
    "electric_heating",
    "tile_stove",
    "fireplace",
    "kitchen_stove",
    "other",
    "no_info",
]

# Default CWU (domestic hot water) hierarchy (ported from divice_dimension.R)
DEFAULT_CWU_HIERARCHY: list[str] = [
    "district_heating",
    "boiler_new",
    "gas_boiler",
    "boiler_old",
    "oil_boiler",
    "heat_pump",
    "electric_heating",
    "tile_stove",
    "fireplace",
    "kitchen_stove",
    "other",
    "no_info",
]

# Default final mapping to canonical names
DEFAULT_FINAL_MAPPING: dict[str, str] = {
    "gas_boiler": "Gas boiler",
    "oil_boiler": "Oil boiler",
    "boiler_new": "New solid fuel boiler (Class 5/Ekoprojekt)",
    "boiler_old": "Old solid fuel boiler (Class 4 or below)",
    "heat_pump": "Heat pump",
    "district_heating": "District heating",
    "electric_heating": "Electric heating",
    "tile_stove": "Tile stove",
    "fireplace": "Fireplace",
    "kitchen_stove": "Kitchen stove",
    "other": "Other",
    "no_info": "No information",
    "solid_fuel_auto": "Solid fuel boiler (automatic feeding)",
    "solid_fuel_manual": "Solid fuel boiler (manual feeding)",
}
