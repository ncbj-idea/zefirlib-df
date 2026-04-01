from sqlalchemy import Column, ForeignKey, Integer, String

from datafusion.database.models.base_class import Base
from datafusion.database.models.import_metadata import ImportMetadata


class MappingImportToTerc(Base):
    __tablename__ = "import_to_terc"
    import_id = Column(
        Integer,
        ForeignKey(f"{ImportMetadata.__tablename__}.id", ondelete="CASCADE"),
        primary_key=True,
    )
    terc = Column(String, primary_key=True)
