from geoalchemy2 import Geometry
from sqlalchemy import Column, ForeignKey, Index, Integer, LargeBinary, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy_json import mutable_json_type

from datafusion.database.db_settings import db_settings
from datafusion.database.models.base_class import Base


class Tile(Base):
    id = Column(Integer, primary_key=True)
    map_id = Column(Integer, ForeignKey("map.id", ondelete="CASCADE"), index=True)
    geom = Column(Geometry("Polygon", spatial_index=False, srid=db_settings.DB_SRID))
    layer = Column(SmallInteger, ForeignKey("kiutlayer.id", ondelete="CASCADE"))
    image = Column(LargeBinary)
    debug = Column(mutable_json_type(dbtype=JSONB, nested=True))

    @declared_attr
    def __table_args__(self) -> tuple[Index]:
        return (
            Index(
                f"idx_{self.__tablename__}_geom",
                "geom",
                postgresql_using="gist",
            ),
        )
