from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, model_validator


class PVGISConfig(BaseModel):
    """
    - lat: Latitude, in decimal degrees, south is negative.
    - lon: Longitude, in decimal degrees, west is negative.
    - peakpower: Nominal power of the PV system, in kW.
    - loss: Sum of system losses, in percent. The estimated system losses are all the losses in the system,
            which cause the power actually delivered to the electricity grid to be lower than the power produced by the
            PV modules.
            There are several causes for this loss, such as losses in cables, power inverters, dirt (sometimes snow) on
            the modules and so on.
            Over the years the modules also tend to lose a bit of their power, so the average yearly output over the
            lifetime of the system
            will be a few percent lower than the output in the first years.
    - startyear: First year of the output of hourly averages.
    - endyear: Final year of the output of hourly averages.
    - trackingtype: Type of suntracking used, 0=fixed, 1=single horizontal axis aligned north-south,
                    2=two-axis tracking,
                    3=vertical axis tracking, 4=single horizontal axis aligned east-west, 5=single inclined axis
                    aligned north-south.
    - optimalangles: Calculate the optimum inclination AND orientation angles. Value of 1 for "yes".
                     All other values (or no value) mean "no".
    - pvtechchoice: PV technology. Choices are: "crystSi", "CIS", "CdTe" and "Unknown".
    - mountingplace: Type of mounting of the PV modules. Choices are: "free" for free-standing and "building"
                     for building-integrated.
                     In PVGIS there are two possibilities: free-standing, meaning that the modules are mounted
                     on a rack with air flowing
                     freely behind the modules; and building- integrated, which means that the modules are completely
                     built into the structure
                     of the wall or roof of a building, with no air movement behind the modules.
    - pvcalculation: If "0" outputs only solar radiation calculations, if "1" outputs the estimation of hourly
                     PV production as well.
    """

    lat: float
    lon: float
    peakpower: float
    loss: float
    startyear: int = 2023
    endyear: int = 2023
    radius: float = 500.0
    trackingtype: Literal[0, 1, 2, 3, 4, 5] = 0
    optimalangles: Literal[0, 1] = 1
    pvtechchoice: Literal["crystSi", "CIS", "CdTe", "Unknown"] = "crystSi"
    mountingplace: Literal["free", "building"] = "building"
    pvcalculation: Literal[0, 1] = 1
    outputformat: str = "json"
    output_path: str | None = None
    tmp_table_schema: str = "tmp"
    base_url: str = "https://re.jrc.ec.europa.eu/api/seriescalc"

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if self.output_path is not None:
            output_path = Path(self.output_path)
            if output_path.exists():
                output_path.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def url_params(self) -> dict:
        return {name: value for name, value in self.__dict__.items() if name != "base_url"}

    def short_rep(self) -> str:
        return (
            f"lat: {self.lat}, lon: {self.lon}, "
            f"peakpower: {self.peakpower}, loss: {self.loss}, "
            f"startyear: {self.startyear}, endyear: {self.endyear}"
        )
