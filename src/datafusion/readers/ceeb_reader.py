import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.database.db_settings import DBSettings
from datafusion.readers.base_reader import Reader
from datafusion.utils.utils import (
    BOOLEAN_COLUMNS,
    EXPECTED_CEEB_DATA_SCHEMA,
    FALSE_VALUES,
    POSSIBLE_STRING_COLUMNS,
    TRUE_VALUES,
    find_delimiter,
    validate_dataframe_by_schema,
)

_logger = logging.getLogger(__name__)


class CEEBReader(Reader):
    """
    Reader class for importing CEEB data into a database.

    This class is responsible for reading CEEB data from specified file paths,
    validating the data schema, and saving the data to the database.
    """

    def __init__(
        self,
        config: CEEBConfig,
        engine: Engine,
        db_settings: DBSettings,
    ) -> None:
        """
        Initializes the CEEBReader.

        Args:
            config (CEEBConfig): Configuration for CEEB data processing.
            engine (Engine): SQLAlchemy engine for connecting to the database.
            db_settings (DBSettings): Database settings for the connection.
        """
        self.config = config
        self.db_settings = db_settings
        self.engine = engine

    def run(self) -> None:
        """
        Executes the CEEB reading process.

        This method orchestrates the reading of CEEB data from the configured
        file paths, processes it, and saves it to the database.
        """
        _logger.info("Running CEEB reader.")
        self._import_id = self._get_import_id()
        self._run_single_data(self.config.ceeb_class_file_path, "ceeb_classes")
        self._run_single_data(self.config.ceeb_devices_file_path, "ceeb_devices")
        _logger.info("CEEB reader done.")

    def _get_import_id(self) -> int:
        """
        Retrieves the import ID for the current CEEB import session.

        Returns:
            int: The import ID for the current import session.
        """
        _logger.info("Getting meta obj")
        meta_obj = self.get_meta_obj(
            table_name="Ceeb_import_data",
            config=self.config,
            engine=self.engine,
            use_tmp_schema=True,
        )
        return meta_obj.id

    def _run_single_data(self, file_path: str, table_name: str) -> None:
        """
        Processes a single data file, validates its schema, and saves it to the database.

        This method reads a CSV file from the specified path, validates its
        structure against the expected schema, adds metadata columns,
        and saves the DataFrame to the corresponding database table.

        Args:
            file_path (str): The file path of the CSV data to process.
            table_name (str): The name of the database table where data will be saved.

        Raises:
            ValueError: If the DataFrame does not conform to the expected schema.

        """
        _logger.info(f"Running CEEB for {table_name=} ...")
        ceeb_df = self.read_from_file(Path(file_path))
        expected_schema: dict[str, list[str]] = EXPECTED_CEEB_DATA_SCHEMA[table_name]
        validate_dataframe_by_schema(ceeb_df, expected_schema)
        ceeb_df["import_id"] = self._import_id
        ceeb_df["terc"] = self.config.terc
        self._save_dataframe_to_db(ceeb_df, table_name)

    def _save_dataframe_to_db(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Saves a DataFrame to the specified database table.

        Args:
            df (pd.DataFrame): The DataFrame to save.
            table_name (str): The name of the table to save data into.
        """
        _logger.info("Saving data to database")
        df.to_sql(
            name=table_name,
            con=self.engine,
            if_exists="replace",
            index=True,
            index_label="id",
        )

    @staticmethod
    def read_from_file(file_path: Path) -> pd.DataFrame:
        """
        Reads a CSV or Excel file into a DataFrame.

        Args:
            file_path (Path): The path to the CSV or Excel file to read.

        Returns:
            pd.DataFrame: The DataFrame containing the data from the file.
        """
        _logger.info("Reading from file %s", file_path)

        # Check file extension to determine the appropriate reader
        if file_path.suffix.lower() in [".xlsx", ".xls"]:
            data = pd.read_excel(
                file_path,
                true_values=TRUE_VALUES,
                false_values=FALSE_VALUES,
            )
        else:
            # Default to CSV for other file types
            delimiter = find_delimiter(file_path)

            data = pd.read_csv(
                file_path,
                delimiter=delimiter,
                true_values=TRUE_VALUES,
                false_values=FALSE_VALUES,
            )

        # Convert boolean columns explicitly (works for both Excel and CSV inputs)
        for col in BOOLEAN_COLUMNS:
            if col in data.columns:
                data[col] = data[col].astype("boolean")

        # Convert string columns to object type (handles int64 being inferred for numeric strings)
        for col in POSSIBLE_STRING_COLUMNS:
            if col in data.columns and data[col].dtype != "object":
                data[col] = data[col].astype("object")

        # Rename columns with variant names to expected names
        column_renames = {
            "Liczba eksploatowanych źródeł ciepła - suma": "Liczba eksploatowanych źródeł ciepła",
            "Liczba zainstalowanych źródeł ciepła - suma": "Liczba zainstalowanych źródeł ciepła",
        }
        data = data.rename(columns=column_renames)

        _logger.info("File has been read")
        return data
