from pathlib import Path

CONFIG_PATH = Path("configs/config.yml")
CONFIG_KEY = "config"
BDOT_BASE_URL = "https://opendata.geoportal.gov.pl/bdot10k/"
POLAND_CS92_SRID = 2180
BACKGROUND_RGBA = (0, 0, 0, 0)
BACKGROUND_RGB = (0, 0, 0)

# Database table names
TABLE_CEEB_DEVICES = "ceeb_devices"
TABLE_CEEB_CLASSES = "ceeb_classes"
TABLE_NON_MERGED_BDOT = "non_merged_bdot"
TABLE_PROCESSED_BDOT = "pyszny_bdot"
TABLE_HEAT_SOURCE_RESULT = "heat_source_result"
TABLE_READY_TO_OPERAT = "ready_to_operat"
TABLE_OPERAT_LOSOWANIA = "operat_losowania"
TABLE_BUILDING_INVENTORY = "building_inventory"
TABLE_SAMPLED_BUILDINGS = "sampled_buildings"

# Heat source result columns (from heat_source_analyzer)
COLUMN_CO_SOURCE = "co_source"  # Central heating source (Polish column name)
COLUMN_CWU_SOURCE = "cwu_source"  # Domestic hot water source
COLUMN_PAIR_WEIGHT = "pair_weight"
COLUMN_BUILDING_TYPE = "building_type"

# Connectivity columns
COLUMN_HEAT_CONNECTED = "heat_connected"
COLUMN_GAS_CONNECTED = "gas_connected"
COLUMN_H3_CONNECTIVITY = "h3_connectivity"

# Functional category column
COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN = "kategoria_funkcjonalna_top_down"

# Heat source type values
VALUE_DISTRICT_HEATING = "Miejska sieć ciepłownicza"  # District heating network
VALUE_GAS_BOILER = "Kocioł gazowy"  # Gas boiler

# Grouping columns for operat losowania
GROUPING_COLUMNS_OPERAT_A = [
    COLUMN_CO_SOURCE,
    COLUMN_CWU_SOURCE,
    COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN,
    COLUMN_H3_CONNECTIVITY,
]

# Grouping columns for operat b
GROUPING_COLUMNS_OPERAT_B = [
    COLUMN_CO_SOURCE,
    COLUMN_CWU_SOURCE,
    COLUMN_H3_CONNECTIVITY,
]
