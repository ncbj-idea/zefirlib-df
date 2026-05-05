from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class DBSettings(BaseSettings):
    POSTGRES_HOST: str
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_PORT: str

    DB_SRID: int = 2180  # Poland CS92
    """
    SRID - Spatial Reference System Identifier
    identifier specifying coordinate system, projection
    and datum for spacial data
    """

    class Config:
        _case_sensitive = True

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


db_settings = DBSettings()
