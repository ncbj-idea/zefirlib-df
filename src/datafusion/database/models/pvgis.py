from sqlalchemy import Column, DateTime, Float, Integer

from datafusion.database.models.base_class import Base


class PVGis(Base):
    """
    P - PV system power units: W
    G_i - Global irradiance on the inclined plane (plane of the array) units: W/m2
    H_sun - Sun height units: degree
    T2m 2-m air temperature units: degree Celsius
    WS10m - 10-m total wind speed: units m/s
    Int - 1 means solar radiation values are reconstructed
    """

    __tablename__: str = "pvgis"

    id = Column(Integer, primary_key=True)
    latitude = Column(Float)
    longitude = Column(Float)
    peakpower = Column(Float)
    loss = Column(Float)
    time = Column(DateTime)
    P = Column(Float)
    Gi = Column(Float)
    H_sun = Column(Float)
    T2m = Column(Float)
    WS10m = Column(Float)
    Int = Column(Float)
