import tempfile

from pydantic import BaseModel, Field


class BordersConfig(BaseModel):
    url: str
    layer_name: str
    tmp_table_name: str
    wfs_version: str
    timeout: int
    tmp_table_schema: str
    tmp_dir_root: str = Field(default_factory=tempfile.gettempdir)
    terc: str | None = None
