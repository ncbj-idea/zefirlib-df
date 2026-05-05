import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_json import mutable_json_type

from datafusion.database.models.base_class import Base


class ImportMetadata(Base):
    __tablename__ = "import_metadata"

    id = Column(Integer, primary_key=True)
    table_name = Column(String)
    import_datetime_utc = Column(DateTime, default=datetime.datetime.now())
    meta = Column(mutable_json_type(dbtype=JSONB, nested=True))
