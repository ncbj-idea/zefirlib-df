from pathlib import Path
from urllib.parse import urljoin

from pydantic import BaseModel

from datafusion.constants import BDOT_BASE_URL
from datafusion.jsons.bdot_mapper import BDOT_MAPPER
from datafusion.utils.utils import read_json


class BDOTConfig(BaseModel):
    url: str | None = None
    terc: str
    layer_name: str = "OT_BUBD_A"
    tmp_table_name: str
    tmp_table_schema: str
    geom_col_name: str
    source_column_map: dict[str, str] | None = None

    def model_post_init(self, __context):
        if not self.url:
            self.url = self._set_url()
        if not self.source_column_map:
            self.source_column_map = BDOT_MAPPER

    def _set_url(self) -> str:
        nr_wojewodztwa = self.terc[:2]
        nr_powiatu = self.terc[2:4]
        return urljoin(BDOT_BASE_URL, f"{nr_wojewodztwa}/{nr_wojewodztwa}{nr_powiatu}_GML.zip")

    @staticmethod
    def _get_map_from_json(file: Path) -> dict[str, str]:
        return read_json(file)
