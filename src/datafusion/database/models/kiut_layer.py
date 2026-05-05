from sqlalchemy import Column, SmallInteger, String

from datafusion.database.models.base_class import Base


class KIUTLayer(Base):
    id = Column(SmallInteger, primary_key=True)
    name = Column(String)
