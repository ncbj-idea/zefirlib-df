from dataclasses import dataclass

from tests.utils import get_resources

CEEB_DEVICES_MOCK_FILE = "ceeb_devices.csv"
CEEB_CLASSES_MOCK_FILE = "ceeb_classes.csv"
BDOT_MOCK_MAPPER = "bdot_mapper.json"
# BDOT_MOCK_MAPPER = {
#     "funogolnabudynku": "funkcja_ogolna",
#     "funszczegolowabudynku": "funkcja_szczegolowa",
#     "liczbakondygnacji": "liczba_kondygnacji",
#     "kodkst": "kst",
#     "zabytek": "czy_zabytek",
# }


@dataclass(frozen=True)
class ResourcesSubDirectory:
    BDOT: str = "bdot"
    CEEB: str = "ceeb"


TEST_DATABASE_CONFIG: dict[str, str] = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_DB": "test_postgres",
    "POSTGRES_USER": "test_postgres",
    "POSTGRES_PASSWORD": "test_postgres",
    "POSTGRES_PORT": "7777",
}


BDOT_CONFIG = {
    "terc": "1863011",
    "layer_name": "OT_BUBD_A",
    "tmp_table_name": "bdot",
    "tmp_table_schema": "tmp",
    "geom_col_name": "geometria",
    "source_column_map": None,
}


TERYT_CONFIG: dict[str, str] = {
    "terc_urzedowy_xml_path": "tests/resources/kiut/TERC_Urzedowy.xml",
}


BORDER_CONFIG = {
    "url": "https://mapy.geoportal.gov.pl/wss/service/PZGIK/PRG/WFS/AdministrativeBoundaries",
    "layer_name": "A05_Granice_jednostek_ewidencyjnych",
    "tmp_table_name": "tmp_administative_boundaries",
    "wfs_version": "1.1.0",
    "timeout": 600,
    "tmp_table_schema": "tmp",
}


KIUT_CONFIG = {
    "terc_urzedowy_xml_path": str(get_resources("kiut/TERC_Urzedowy")),
    "terc": "2212011",
    "layers": ["przewod_cieplowniczy", "przewod_gazowy"],
    "polygonization": {
        "grid_existence_threshold": 0.005,
        "method": "ANALYZE_COLORS_ON_MAP",
        "background_rgba": "0, 0, 0, 0",
    },
    "wms": {
        "bbox_size": 500,
        "image_size": 1000,
        "url": "https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaUzbrojeniaTerenu",
        "version": "1.3.0",
        "srid": 2180,
    },
    "number_of_slices_of_image_side": 50,
}


CEEB_CONFIG: dict[str, str] = {
    "terc": "2212011",
    "ceeb_devices_file_path": str(get_resources(f"{ResourcesSubDirectory.CEEB}/{CEEB_DEVICES_MOCK_FILE}")),
    "ceeb_class_file_path": str(get_resources(f"{ResourcesSubDirectory.CEEB}/{CEEB_CLASSES_MOCK_FILE}")),
    "tmp_table_schema": "tmp",
}


CONFIG = {
    "bdot": BDOT_CONFIG,
    "kiut": KIUT_CONFIG,
    "ceeb": CEEB_CONFIG,
    "borders": BORDER_CONFIG,
    "teryt": TERYT_CONFIG,
}

ADDRESS_CONFIG = {
    "terc": "0201011",
    "url": "https://opendata.geoportal.gov.pl/prg/adresy/",
    "layer_name": "PRG_PunktAdresowy",
    "tmp_table_name": "tmp_address_point_02",
    "tmp_table_schema": "tmp",
    "geometry_column_name": "pozycja",
}

GLOBAL_CONFIG = {
    "terc": "1863011",
    "output_path": "output/test",
}

PVGIS_CONFIG = {
    "lat": 52.403,
    "lon": 20.916,
    "peakpower": 1.0,
    "loss": 14,
    "startyear": 2023,
    "endyear": 2023,
    "radius": 500.0,
}


MERGE_CONFIG = {
    "terc": "2212011",
    "h3_resolution": 7,
    "gini_in_topsis": False,
    "gini_lorenz": False,
    "gini_method": "trapz",
    "classification_method": "topsis",
    "coord_system": "EPSG:2180",
    "complex_distance": 10,
    "string_max_distance": 0.1,
    "string_param": 1,
    "string_method": "cosine",
    "heat_threshold": 0.5,
    "heat_development": "h3",
    "expanded_logs": True,
    "trash_treshold": 0.25,
    "avg_flat": 68.3,
    "gus_multiplicator": 1,
    "ceeb_params": {
        "ceeb_merger": [
            "Typ_deklaracji",
            "ulica",
            "numer_porzadkowy",
        ],
        "ceeb_boiler": [
            (
                "Kocioł na paliwo stałe (węgiel, drewno, pellet lub inny rodzaj biomasy) "
                "z ręcznym podawaniem paliwa / zasypowy"
            ),
            (
                "Kocioł na paliwo stałe (węgiel, drewno, pellet lub inny rodzaj biomasy) "
                "z automatycznym podawaniem paliwa / z podajnikiem"
            ),
        ],
        "ceeb_summary": [
            "Typ_deklaracji",
            "ulica",
            "numer_porzadkowy",
            "Klasa_kotła",
        ],
        "ceeb_living": [
            "A",
        ],
        "ceeb_non_living": [
            "B",
        ],
        "ceeb_diverge": "Numer_domu",
        "ceeb_important_col": [
            "Typ_deklaracji",
            "ulica",
            "numer_porzadkowy",
            "Źródło_ciepła",
        ],
        "ceeb_device_col": "Źródło_ciepła",
        "ceeb_street_col": "Ulica",
        "ceeb_number_col": "Numer_budynku",
        "ceeb_class_col": "Klasa_kotła",
        "ceeb_declare_col": "Typ_deklaracji",
        "ceeb_eksp_col": "Liczba_eksploatowanych_źródeł_ciepła",
        "ceeb_nmb_col": "Liczba_zainstalowanych_źródeł_ciepła",
        "ceeb_lokal_col": "Numer_lokalu",
        "ceeb_cwu": "C.W.U.",
        "ceeb_co": "C.O.",
        "ind_var": [
            "Poniżej_klasy_3_lub_brak_informacji",
            "Klasa_3",
            "Klasa_4",
            "Klasa_5",
            "Ekoprojekt",
        ],
    },
    "bdot_params": {
        "bdot_street_col": "ulica",
        "bdot_number_col": "numer_porzadkowy",
        "bdot_geom_var": "geom_wkt",
        "bdot_binary_var": [
            "heat_connected",
            "gas_connected",
            "h3_connectivity",
        ],
        "bdot_sum_var": [
            "pow_obrysu_m2",
            "pow_uzytkowa_m2",
            "n",
        ],
        "bdot_addr_var": [
            "ulica",
            "numer_porzadkowy",
            "longitude_centroid",
            "latitude_centroid",
            "addr_distance",
            "wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy",
            "nazwa_funkcji_ogolnej",
            "funkcja_szczegolowa_budynku",
            "classification",
            "index",
            "bdot_key",
        ],
        "bdot_addr_distance": "addr_distance",
        "bdot_id": "id",
        "bdot_merge_var": "nazwa_funkcji_ogolnej",
        "bdot_col_output": [
            "longitude_centroid",
            "latitude_centroid",
            "wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy",
            "funkcja_szczegolowa_budynku",
            "classification",
            "index",
        ],
        "h3_excluded_type": [
            "produkcyjny",
            "hala widowiskowa",
            "hipermarket lub supermarket",
            "dom towarowy lub handlowy",
            "hala sportowa",
            "pływalnia",
            "hala targowa -  do spawdzenia",
            "parking wielopoziomowy",
            "sztuczne lodowisko",
        ],
        "bdot_floors": "liczba_kondygnacji",
        "bdot_pow_uzytkow": "pow_uzytkowa_m2",
        "bdot_obrys": "pow_obrysu_m2",
        "bdot_detail": "funkcja_szczegolowa_budynku",
        "bdot_heat": "heat_connected",
        "heat_distance": "heat_distance",
        "non_inventory_build": [
            "budynek gospodarczy",
            "hala targowa -  do spawdzenia",
            "hala sportowa",
            "hala widowiskowa",
            "halowy tor gokartowy",
            "dom towarowy lub handlowy",
            "garaż",
            "budynek produkcyjny zwierząt hodowlanych",
            "hala wystawowa",
            "korty tenisowe",
            "produkcyjny",
            "pływalnia",
            "stacja transformatorowa",
            "szklarnia lub cieplarnia",
            "toaleta publiczna",
            "ujeżdżalnia",
            "elewator",
        ],
        "living_bdot": [
            "Budynki o trzech i więcej mieszkaniach",
            "Budynki mieszkalne jednorodzinne",
            "Budynki o dwóch mieszkaniach i wielomieszkaniowe",
        ],
        "multifamily_bdot": [
            "budynek wielorodzinny",
            "budynek o dwóch mieszkaniach",
        ],
    },
    "joining_params": {
        "var_ceeb": "Rodzaj_budynku_A",
        "ceeb_single": "Budynek jednorodzinny (w tym w zabudowie bliźniaczej i szeregowej)",
        "ceeb_multi": "Budynek wielorodzinny",
        "ceeb_other": "Budynek zbiorowego zamieszkania",
        "single_order": [
            "Budynki mieszkalne jednorodzinne",
            "Budynki o dwóch mieszkaniach i wielomieszkaniowe",
            "Budynki o trzech i więcej mieszkaniach",
            "Budynki zbiorowego zamieszkania",
            "others",
        ],
        "multi_order": [
            "Budynki o trzech i więcej mieszkaniach",
            "Budynki o dwóch mieszkaniach i wielomieszkaniowe",
            "Budynki zbiorowego zamieszkania",
            "Budynki mieszkalne jednorodzinne",
            "others",
        ],
        "other_order": [
            "Budynki zbiorowego zamieszkania",
            "Budynki o dwóch mieszkaniach i wielomieszkaniowe",
            "Budynki o trzech i więcej mieszkaniach",
            "Budynki mieszkalne jednorodzinne",
            "others",
        ],
        "nonliving_order": [
            "Budynki o trzech i więcej mieszkaniach",
            "Budynki o dwóch mieszkaniach i wielomieszkaniowe",
            "Budynki mieszkalne jednorodzinne",
        ],
    },
}


POSTPROCESSING_CONFIG = {
    "terc": "1863011",
    "input_path": "output/test",
    "output_path": "output/test",
}
