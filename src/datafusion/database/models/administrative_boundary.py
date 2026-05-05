from geoalchemy2 import Geometry
from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlalchemy.ext.declarative import declared_attr

from datafusion.database.models.base_class import Base
from datafusion.database.session import db_settings


class AdministrativeBoundary(Base):
    __tablename__ = "administrative_boundary"
    terc = Column(String(7), primary_key=True)
    import_id = Column(Integer, ForeignKey("import_metadata.id", ondelete="CASCADE"), primary_key=True)
    name = Column(String)
    geom = Column(Geometry("Multipolygon", spatial_index=False, srid=db_settings.DB_SRID))  # type: ignore # noqa

    @declared_attr
    def __table_args__(self) -> tuple[Index]:
        return (
            Index(
                f"idx_{self.__tablename__}_geom",
                "geom",
                postgresql_using="gist",
            ),
        )
