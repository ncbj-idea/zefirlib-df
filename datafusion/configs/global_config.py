from pathlib import Path

from pydantic import BaseModel


class GlobalConfig(BaseModel):
    """
    Global configuration containing shared settings across all modules.

    Attributes:
        terc (str): TERC (Territorial Electronic Register of Territorial Units)
                   number - identification code of territorial unit in Poland
        output_folder (Path): Unified output folder for all modules
    """

    terc: str
    output_folder: Path = Path("output")
    input_folder: Path = Path("input")
