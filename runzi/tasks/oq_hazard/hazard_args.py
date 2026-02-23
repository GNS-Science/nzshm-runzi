"""This module provides the Pydantic intput parameter classes of hazard and disaggregation caculations."""

from pathlib import Path
from typing import Annotated, Any, Optional

from nzshm_common import CodedLocation
from nzshm_model import all_model_versions
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)
from toshi_hazard_store.model import AggregationEnum

try:
    from toshi_hazard_store.scripts.ths_import import chc_manager
except ImportError:
    print("openquake not installed, not importing toshi-hazard-store chc_manager")
from typing_extensions import Self


def _is_model_version(value: str | None) -> str | None:
    if (value is not None) and (value not in all_model_versions()):
        raise ValueError(f"must specify valid nshm_model_version ({all_model_versions()})")
    return value


def _has_vs30(filepath: Path):
    with filepath.open() as lf:
        header = lf.readline()
        if "vs30" in header:
            return True
    return False


def _is_compat_calc_id(compat_calc_id: str) -> str:
    try:
        if not chc_manager.load(compat_calc_id):
            raise ValueError(f"Compatible Hazard Calculation with unique ID {compat_calc_id} does not exist.")
    except FileNotFoundError:
        raise ValueError(f"Compatible Hazard Calculation with unique ID {compat_calc_id} does not exist.")

    return compat_calc_id


class OQArgs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)  # this allows OpenquakeConfig to be included in the schema

    # define the hazard model (LTs). (for disagg this must be the same as the target curve).
    compatible_calc_id: Annotated[str, AfterValidator(_is_compat_calc_id)]
    nshm_model_version: Annotated[Optional[str], AfterValidator(_is_model_version)] = None
    srm_logic_tree: Optional[SourceLogicTree | Path] = None
    gmcm_logic_tree: Optional[GMCMLogicTree | Path] = None
    hazard_config: Optional[OpenquakeConfig | Path] = None

    # the site
    vs30: Optional[PositiveInt] = None
    locations: Optional[list[str]] = None
    locations_file: Optional[Path] = None
    locations_file_id: Optional[str] = None

    @model_validator(mode='after')
    def check_logic_trees(self) -> Self:
        if not self.nshm_model_version and not (self.srm_logic_tree and self.gmcm_logic_tree and self.hazard_config):
            raise ValueError(
                """if nshm_model_version not specified, must provide all of
                gmcm_logic_tree, srm_logic_tree, and hazard_config."""
            )
        return self

    @field_validator('srm_logic_tree', 'gmcm_logic_tree', 'hazard_config', 'locations_file', mode='after')
    @classmethod
    def abs_path(cls, value: Any, info: ValidationInfo) -> Any:
        """If any of the fields are paths, resolve the absolute path and check that it exists."""
        if isinstance(value, Path):
            file_path = value
            if not file_path.is_absolute():
                if isinstance(info.context, dict):
                    base_path = info.context.get("base_path")
                    if base_path is not None:
                        file_path = (Path(base_path) / file_path).resolve()
            if not file_path.exists():
                raise ValueError(f"file {value} does not exist")
            return file_path
        return value

    # OpenquakeConfig is not a dataclass so we have to tell pydantic how to serialize it
    @field_serializer('hazard_config', mode='plain')
    def ser_hazard_config(self, value: Any) -> Any:
        if isinstance(value, OpenquakeConfig):
            return value.to_dict()
        return value

    # OpenquakeConfig is not a dataclass so we have to tell pydantic how to validate it
    @field_validator('hazard_config', mode='before')
    @classmethod
    def validate_hazard_config(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return OpenquakeConfig.from_dict(value)
        return value

    @model_validator(mode='after')
    def check_locations(self) -> Self:
        if self.locations_file and self.locations:
            raise ValueError("cannot specify both locations and locations_file")
        if not (self.locations_file or self.locations):
            raise ValueError("must specify one of locations or locations_file")

        file_has_vs30 = self.locations_file and _has_vs30(self.locations_file)
        if file_has_vs30 and self.vs30:
            raise ValueError("cannot specify both uniform and site-specific vs30")
        elif not file_has_vs30 and not self.vs30:
            raise ValueError("locations file must have vs30 column if uniform vs30 not given")

        return self


class OQDisaggArgs(OQArgs):
    """Input for calculating disaggregations."""

    # We use the site member to specify a unique vs30 and location. This makes it possible to sweep over all site
    # conditions specifed by the location, vs30, etc. members that are in OQArgs. This is only used by the task, not
    # meant to be set by the user
    class Site(BaseModel):
        location: CodedLocation
        vs30: PositiveInt

    site: Optional[Site] = None

    # the hazard curve "target," i.e. the hazard curve at which to get the PoE that we will use for the disaggregation
    hazard_model_id: str
    agg: AggregationEnum
    imt: str
    investigation_time: int
    poe: float

    # defines the disaggregation to calculate (what types, bins, etc.)
    disagg_types: list[str]
    mag_bin_width: Optional[float] = None
    distance_bin_width: Optional[float] = None
    coordinate_bin_width: Optional[float] = None
    num_epsilon_bins: Optional[int] = None
    disagg_bin_edges: dict[str, list[float]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_bins(self) -> Self:
        for key in self.disagg_bin_edges.keys():
            match key:
                case "mag":
                    if self.mag_bin_width:
                        raise ValueError("cannot specify mag_bin_width and mag bin edges")
                case "dist":
                    if self.distance_bin_width:
                        raise ValueError("cannot specify distance_bin_width and dist bin edges")
                case "lon":
                    if self.coordinate_bin_width:
                        raise ValueError("cannot specify coordinate_bin_width and lon bin edges")
                case "lat":
                    if self.coordinate_bin_width:
                        raise ValueError("cannot specify coordinate_bin_width and lat bin edges")
                case "eps":
                    if self.num_epsilon_bins:
                        raise ValueError("cannot specify num_epsilon_bins and eps bin edges")
                case undef:
                    raise ValueError("invalid bin edge category {}".format(undef))

        return self

    @model_validator(mode='after')
    def valdiate_types(self) -> Self:
        for disagg_type in set("_".join(self.disagg_types).split("_")):
            match disagg_type:
                case "Mag":
                    if not ("mag" in self.disagg_bin_edges or self.mag_bin_width):
                        raise ValueError("magnitude disaggregation requires mag_bin_width or bin edges")
                case "Dist":
                    if not ("dist" in self.disagg_bin_edges or self.distance_bin_width):
                        raise ValueError("distance disaggregation requires distance_bin_width or bin edges")
                case "Lon":
                    if not ("lon" in self.disagg_bin_edges or self.coordinate_bin_width):
                        raise ValueError("longitude disaggregation requries coordiate_bin_width or lon bin edges")
                case "Lat":
                    if not ("lat" in self.disagg_bin_edges or self.coordinate_bin_width):
                        raise ValueError("latitude disaggregation requries coordiate_bin_width or lat bin edges")
                case "TRT":
                    pass
                case "Eps":
                    if not ("eps" in self.disagg_bin_edges or self.num_epsilon_bins):
                        raise ValueError("epsilon disaggregation requries num_epsilon_bins or bin edges")
                case undef:
                    raise ValueError("unrecognized disaggregation type {}".format(undef))

        return self


class OQHazardArgs(OQArgs):
    """Input for calculating hazard curves."""

    imts: list[str]
    imtls: list[float]
