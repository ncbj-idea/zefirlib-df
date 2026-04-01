import os

from pydantic import BaseModel, model_validator


class CEEBConfig(BaseModel):
    """
    Configuration model for CEEB application file paths and schema.

    Attributes:
        terc (str): Terc code used in import statements
        ceeb_devices_file_path (str): Path to the CSV or Excel file containing CEEB device data.
        ceeb_class_file_path (str): Path to the CSV or Excel file containing CEEB class data.
        tmp_table_schema (str): Temporary table schema name used in the application.
        skip_file_validation (bool): If True, skips file existence validation.
    """

    terc: str
    ceeb_devices_file_path: str
    ceeb_class_file_path: str
    tmp_table_schema: str
    skip_file_validation: bool = False

    @model_validator(mode="after")
    def validate_files(self) -> "CEEBConfig":
        """Validate that files exist and have supported extensions."""
        if self.skip_file_validation:
            return self

        for path_attr in ["ceeb_devices_file_path", "ceeb_class_file_path"]:
            path = getattr(self, path_attr)
            if not os.path.isfile(path):
                raise ValueError(f"File '{path}' does not exist.")
            allowed_ext = (".csv", ".xlsx", ".xls")
            if not any(path.endswith(ext) for ext in allowed_ext):
                raise ValueError(f"File '{path}' must have one of the supported extensions: {', '.join(allowed_ext)}.")

        return self
