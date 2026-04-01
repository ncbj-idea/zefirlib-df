from geoalchemy2 import Geometry
from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlalchemy_json import mutable_json_type

from datafusion.database.models.base_class import Base
from datafusion.database.session import db_settings


class AddressPoint(Base):
    __tablename__: str = "address_point"

    id = Column(Integer, primary_key=True)
    import_id = Column(Integer, ForeignKey("import_metadata.id", ondelete="CASCADE"))
    miejscowosc = Column(String)
    kod_pocztowy = Column(String(6))
    ulica = Column(String)
    numer_porzadkowy = Column(String)
    geom = Column(Geometry("Point", spatial_index=False, srid=db_settings.DB_SRID))
    other = Column(mutable_json_type(dbtype=JSONB, nested=True))
    latitude = Column(Float)
    longitude = Column(Float)

    @declared_attr
    def __table_args__(self):
        return (
            Index(
                f"idx_{self.__tablename__}_geom",
                "geom",
                postgresql_using="gist",
            ),
        )
