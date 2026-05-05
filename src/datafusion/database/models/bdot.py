from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlalchemy_json import mutable_json_type

from datafusion.database.db_settings import db_settings
from datafusion.database.models.base_class import Base


class BDOT10k(Base):
    __tablename__ = "bdot10k"

    id = Column(Integer, primary_key=True)
    import_id = Column(Integer, ForeignKey("import_metadata.id", ondelete="CASCADE"))
    identyfikator = Column(String)
    funkcja_ogolna = Column(String)
    funkcja_szczegolowa = Column(postgresql.ARRAY(String))
    liczba_kondygnacji = Column(Integer)
    kst = Column(String)
    czy_zabytek = Column(Boolean)
    other = Column(mutable_json_type(dbtype=JSONB, nested=True))
    geom = Column(Geometry("Multipolygon", spatial_index=False, srid=db_settings.DB_SRID))

    @declared_attr
    def __table_args__(self) -> tuple[Index]:
        return (
            Index(
                f"idx_{self.__tablename__}_geom",
                "geom",
                postgresql_using="gist",
            ),
        )
