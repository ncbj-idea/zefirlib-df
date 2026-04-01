from datafusion import get_resource_path


def get_building_parameters_path() -> str:
    return str(get_resource_path("building_parameters.xlsx"))
