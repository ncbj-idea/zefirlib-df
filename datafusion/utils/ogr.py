import logging
import subprocess
from pathlib import Path

from datafusion.database.db_settings import DBSettings

_logger = logging.getLogger(__name__)


class OgrCaller:
    def __init__(
        self,
        table_name: str,
        layer_name: str | None = None,
        layer_type: str = "PROMOTE_TO_MULTI",
        replace: bool = True,
        fixed_axis_order: bool = False,
        use_layer_name: bool = True,
    ) -> None:
        self.table_name = table_name
        self.layer_name = layer_name
        self.layer_type = layer_type
        self.replace = replace
        self.fixed_axis_order = fixed_axis_order
        self.use_layer_name = use_layer_name

    def __call__(self, file: Path, db_settings: DBSettings, replace: bool = True) -> None:
        db_params = (
            f"PG:host={db_settings.POSTGRES_HOST} "
            f"user={db_settings.POSTGRES_USER} "
            f"port={db_settings.POSTGRES_PORT} "
            f"password={db_settings.POSTGRES_PASSWORD} "
            f"dbname={db_settings.POSTGRES_DB}"
        )
        cmd = [
            "ogr2ogr",
            "-f",
            "PostgreSQL",
            db_params,
            str(file),
            "-nln",
            self.table_name,
            "-forceNullable",
            "-lco",
            "PRECISION=no",
            "-oo",
            "FORCE_SRS_DETECTION=YES",
        ]

        # Only add layer name if explicitly requested and provided
        if self.use_layer_name and self.layer_name:
            cmd.append(self.layer_name)
        if self.layer_type:
            cmd += ["-nlt", self.layer_type]
        if self.replace:
            cmd += ["-overwrite"]
        else:
            cmd += ["-append", "-update"]
        if self.fixed_axis_order:
            cmd += ["-oo", "INVERT_AXIS_ORDER_IF_LAT_LONG=NO"]  # per dedault is `YES`

        # if source_crs:
        #     cmd += ["-a_srs", source_crs]

        try:
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            _logger.exception(
                "An error occured during ogr2ogr call with context\nstdderr:\n%sstdout:\n%sreturn code: %s",
                e.stderr,
                e.stdout,
                e.returncode,
            )
            raise
        if output.stderr:
            _logger.warning("Warning: %s %s", output.stderr, output.stdout)
