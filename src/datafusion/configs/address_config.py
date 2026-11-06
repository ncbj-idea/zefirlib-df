from pydantic import BaseModel, Field


class AddressConfig(BaseModel):
    terc: str
    teryt: str | None = None
    url: str
    layer_name: str
    tmp_table_name: str
    tmp_table_schema: str = "tmp"
    geometry_column_name: str = "geometria"
    wfs_version: str = "2.0.0"
    timeout: int = 600
    srid: int = 2180
    page_size: int = Field(default=10000, gt=0)

    def model_post_init(self, __context):
        if not self.teryt:
            self.teryt = self._extract_teryt_from_terc()

    def _extract_teryt_from_terc(self) -> str:
        """Extract TERYT code (voivodeship code) from TERC code.
        TERC format: WWPPGG (where WW = voivodeship, PP = county, GG = municipality)
        TERYT is the voivodeship code (first 2 digits)
        """
        return self.terc[:2]


__all__ = ["AddressConfig"]
