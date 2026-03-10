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
from runzi.tasks.validators import resolve_path
from toshi_hazard_store.config import STORAGE_FOLDER
from toshi_hazard_store.model import AggregationEnum
from toshi_hazard_store.model.hazard_models_manager import CompatibleHazardCalculationManager
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
    chc_manager = CompatibleHazardCalculationManager(Path(STORAGE_FOLDER))
    try:
        if not chc_manager.load(compat_calc_id):
            raise ValueError(f"Compatible Hazard Calculation with unique ID {compat_calc_id} does not exist.")
    except FileNotFoundError:
        raise ValueError(f"Compatible Hazard Calculation with unique ID {compat_calc_id} does not exist.")

    return compat_calc_id


class OQArgs(BaseModel):
    """Base class for OpenQuake task arguments.

    Validators:
        - If nshm_model_version not given, must provide srm_logic_tree, gmcm_logic_tree, and hazard_config.
        - All files must exist either relative to input file or as absolute path.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)  # this allows OpenquakeConfig to be included in the schema

    # define the hazard model (LTs). (for disagg this must be the same as the target curve).
    compatible_calc_id: Annotated[str, AfterValidator(_is_compat_calc_id)]
    """Identifies hazard run with similar software and settigs such that results can be compared."""

    nshm_model_version: Annotated[Optional[str], AfterValidator(_is_model_version)] = None
    """An official released NSHM model. Includes logic trees and calculation configuration (i.e. OQ settings)."""

    srm_logic_tree: Optional[SourceLogicTree | Path] = None
    """Seismicity rate model logic tree."""

    gmcm_logic_tree: Optional[GMCMLogicTree | Path] = None
    """Ground motion model logic tree."""

    hazard_config: Optional[OpenquakeConfig | Path] = None
    """OpenQuake settings."""

    # the site
    vs30: Optional[PositiveInt] = None
    """Uniform site vs30."""

    locations: Optional[list[str]] = None
    """Location strings as used by nzshm-common."""

    locations_file: Optional[Path] = None
    """A file with lon, lat locations, and optinoally vs30."""

    locations_file_id: Optional[str] = None
    """A toshi ID of a file with lon, lat locations, and optinoally vs30."""

    @model_validator(mode='after')
    def check_logic_trees(self) -> Self:
        if not self.nshm_model_version and not (self.srm_logic_tree and self.gmcm_logic_tree and self.hazard_config):
            raise ValueError("""if nshm_model_version not specified, must provide all of
                gmcm_logic_tree, srm_logic_tree, and hazard_config.""")
        return self

    @field_validator('srm_logic_tree', 'gmcm_logic_tree', 'hazard_config', 'locations_file', mode='after')
    @classmethod
    def abs_path(cls, value: Any, info: ValidationInfo) -> Any:
        """If any of the fields are paths, resolve the absolute path and check that it exists."""
        return resolve_path(value, info)

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
    """Input for calculating disaggregations.

    Validators:
        - Cannot combine bin width or number of bins with bin edges.
        - Must provide bin width, number, or edges for every dimension in disagg_types.
    """

    # We use the site member to specify a unique vs30 and location. This makes it possible to sweep over all site
    # conditions specifed by the location, vs30, etc. members that are in OQArgs. This is only used by the task, not
    # meant to be set by the user
    class Site(BaseModel):
        """A location, vs30 pair. Not a user object."""

        location: CodedLocation
        vs30: PositiveInt

    site: Optional[Site] = None
    """Used by runzi to create a unique task for each location, vs30 pair, not to be set by user."""

    hazard_model_id: str
    """The hazard curve 'target,' i.e. the hazard curve at which to get the PoE that we will use
    for the disaggregation.
    """

    agg: AggregationEnum
    """The aggregate of the hazard curve 'target,' i.e. the hazard curve at which to get the PoE
    that we will use for the disaggregation.
    """

    imt: str
    """The IMT of the hazard curve 'target,' i.e. the hazard curve at which to get the PoE that we
    will use for the disaggregation.
    """

    investigation_time: int
    """The investigation time (years) of the hazard curve 'target,' i.e. the hazard curve at which
    to get the PoE that we will use for the disaggregation.
    """

    poe: float
    """The probability of exceedance for the investigation_time for the hazard curve 'target,' i.e.
    the hazard curve at which to get the PoE that we will use for the disaggregation.
    """

    # defines the disaggregation to calculate (what types, bins, etc.)
    disagg_types: list[str]
    """Dimensions along which to calculate disaggregation. e.g. 'Mag', 'Dist', 'TRT_Mag_Dist_Eps'"""
    mag_bin_width: Optional[float] = None
    distance_bin_width: Optional[float] = None
    coordinate_bin_width: Optional[float] = None
    num_epsilon_bins: Optional[int] = None
    disagg_bin_edges: dict[str, list[float]] = Field(default_factory=dict)
    """Dict of disaggregation bin edges. Keys are dimentions (e.g. 'dist'), values are
    the edges (e.g. [0, 5.0, 10.0, ]).
    """

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
