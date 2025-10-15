"""This module provides the Pydantic intput parameter classes of hazard and disaggregation caculations."""

from pathlib import Path
from typing import Any, ClassVar, Dict, Optional, Union

import tomlkit
from nzshm_model import all_model_versions
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FilePath,
    PositiveInt,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)
from toshi_hazard_store.model import AggregationEnum

from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType

try:
    from toshi_hazard_store.scripts.ths_import import chc_manager
except ImportError:
    print("openquake not installed, not importing toshi-hazard-store chc_manager")
from typing_extensions import Annotated, Self


def is_model_version(value: str) -> str:
    if value not in all_model_versions():
        raise ValueError("must specify valid nshm_model_version ({})".format(all_model_versions()))
    return value


def is_compat_calc_id(compat_calc_id: str) -> str:
    try:
        if not chc_manager.load(compat_calc_id):
            raise ValueError(f"Compatible Hazard Calculation with unique ID {compat_calc_id} does not exist.")
    except FileNotFoundError:
        raise ValueError(f"Compatible Hazard Calculation with unique ID {compat_calc_id} does not exist.")

    return compat_calc_id


def resolve_path(path: Union[Path, str], reference_filepath: Union[Path, str]) -> str:
    path = Path(path).expanduser()
    if not path.is_absolute():
        return str(Path(reference_filepath).parent / path)
    return str(path)


def coerce_to_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return [value]
    return value


class General(BaseModel):
    title: str
    description: str = ''
    compatible_calc_id: Annotated[str, AfterValidator(is_compat_calc_id)]


class HazardModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    nshm_model_version: Annotated[Optional[str], AfterValidator(is_model_version)] = None

    srm_logic_tree: Optional[FilePath | SourceLogicTree] = None
    gmcm_logic_tree: Optional[FilePath | GMCMLogicTree] = None
    hazard_config: Optional[FilePath | OpenquakeConfig] = None

    @model_validator(mode='after')
    def check_logic_trees(self) -> Self:
        if not self.nshm_model_version and not (self.srm_logic_tree and self.gmcm_logic_tree and self.hazard_config):
            raise ValueError(
                """if nshm_model_version not specified, must provide all of
                gmcm_logic_tree, srm_logic_tree, and hazard_config file paths"""
            )
        return self

    # OpenquakeConfig is not a dataclass so we have to tell pydantic how to serialize it
    @field_serializer('hazard_config', mode='plain')
    def ser_hazard_config(self, value: Any) -> Any:
        if isinstance(value, OpenquakeConfig):
            return value.to_dict()
        return value

    # OpenquakeConfig is not a dataclass so we have to tell pydantic how to validate it
    @field_validator('hazard_config', mode='before')
    def validate_hazard_config(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return OpenquakeConfig.from_dict(value)
        return value


class HazardCurve(BaseModel):
    imts: Annotated[list[str], BeforeValidator(coerce_to_list)]
    imtls: Annotated[list[float], BeforeValidator(coerce_to_list)]


class HazardSite(BaseModel):
    # TODO: this is another swept argument used as a scalar in the task. Not sure how to fix here
    vs30s: Annotated[Optional[list[PositiveInt]], BeforeValidator(coerce_to_list)] = None
    locations: Annotated[Optional[list[str]], BeforeValidator(coerce_to_list)] = None
    locations_file: Optional[FilePath] = None
    locations_file_id: Optional[str] = None

    @staticmethod
    def has_vs30(filepath: Path):
        with filepath.open() as lf:
            header = lf.readline()
            if "vs30" in header:
                return True
        return False

    @model_validator(mode='after')
    def check_locations(self) -> Self:
        if self.locations_file and self.locations:
            raise ValueError("cannot specify both locations and locations_file")
        if not (self.locations_file or self.locations):
            raise ValueError("must specify one of locations or locations_file")

        file_has_vs30 = self.locations_file and self.has_vs30(self.locations_file)
        if file_has_vs30 and self.vs30s:
            raise ValueError("cannot specify both uniform and site-specific vs30")
        elif not file_has_vs30 and not self.vs30s:
            raise ValueError("locations file must have vs30 column if uniform vs30 not given")

        return self


class DisaggCurve(BaseModel):
    hazard_model_id: Annotated[str, AfterValidator(is_model_version)]
    aggs: Annotated[list[AggregationEnum], BeforeValidator(coerce_to_list)]
    imts: Annotated[list[str], BeforeValidator(coerce_to_list)]


class DisaggProb(BaseModel):
    inv_time: int
    poes: Annotated[list[float], BeforeValidator(coerce_to_list)]
    disagg_outputs: Annotated[list[str], BeforeValidator(coerce_to_list)]
    mag_bin_width: Optional[float] = None
    distance_bin_width: Optional[float] = None
    coordinate_bin_width: Optional[float] = None
    num_epsilon_bins: Optional[int] = None
    disagg_bin_edges: Dict[str, list[float]] = Field(default_factory=dict)

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
        for output_type in set("_".join(self.disagg_outputs).split("_")):
            match output_type:
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


class DisaggOutput(BaseModel):
    gt_filename: str


class HazardInputBase(BaseModel):
    task_type: ClassVar[HazardTaskType]
    filepath: FilePath
    general: General
    hazard_model: HazardModel
    site_params: HazardSite

    @classmethod
    def from_toml(cls, toml_filepath: Path | str) -> Self:
        """Creates a hazard input object from a toml file.

        Args:
            toml_file: Path to TOML file.

        Returns:
            An instance of the class initialized with the TOML file.
        """
        with Path(toml_filepath).open() as f:
            content = f.read()
        data = tomlkit.parse(content).unwrap()
        data["filepath"] = Path(toml_filepath).absolute()
        # TODO: I like to use strict=True but it seems to cause issues with FilePath type. Could
        # use field to specify strict=False just for that field maybe?
        return cls.model_validate(data)

    # resolve absolute paths (relative to input file) for optional logic tree and config fields
    @field_validator('hazard_model', mode='before')
    @classmethod
    def absolute_model_paths(cls, data: Any, info: ValidationInfo) -> Any:
        if isinstance(data, dict):
            for key in ["srm_logic_tree", "gmcm_logic_tree", "hazard_config"]:
                if isinstance(data.get(key), str):
                    data[key] = resolve_path(data[key], info.data["filepath"])
        return data

    # resolve absolute paths (relative to input file) for optional site file
    @field_validator('site_params', mode='before')
    @classmethod
    def absolute_site_path(cls, data: Any, info: ValidationInfo) -> Any:
        if isinstance(data, dict):
            if data.get("locations_file"):
                data["locations_file"] = resolve_path(data["locations_file"], info.data["filepath"])
        return data


class HazardInput(HazardInputBase):
    """Input for calculating hazard curves."""

    task_type: HazardTaskType = Field(default=HazardTaskType.HAZARD, frozen=True)
    hazard_curve: HazardCurve


class DisaggInput(HazardInputBase):
    """Input for calculating disaggregations."""

    task_type: HazardTaskType = Field(default=HazardTaskType.DISAGG, frozen=True)
    disagg: DisaggProb
    output: DisaggOutput
    hazard_curve: DisaggCurve
