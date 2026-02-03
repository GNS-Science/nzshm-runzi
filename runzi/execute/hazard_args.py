"""This module provides the Pydantic intput parameter classes of hazard and disaggregation caculations."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

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


class HazardModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    nshm_model_version: Annotated[Optional[str], AfterValidator(is_model_version)] = None

    srm_logic_tree: Optional[SourceLogicTree | Path] = None
    gmcm_logic_tree: Optional[GMCMLogicTree | Path] = None
    hazard_config: Optional[OpenquakeConfig | Path] = None

    @model_validator(mode='after')
    def check_logic_trees(self) -> Self:
        if not self.nshm_model_version and not (self.srm_logic_tree and self.gmcm_logic_tree and self.hazard_config):
            raise ValueError(
                """if nshm_model_version not specified, must provide all of
                gmcm_logic_tree, srm_logic_tree, and hazard_config."""
            )
        return self

    #TODO: convert to annotated aren re-use on site    
    @field_validator('srm_logic_tree', 'gmcm_logic_tree', 'hazard_config', mode='after')
    @classmethod
    def abs_path(cls, value: OpenquakeConfig | Path | None, info: ValidationInfo) -> OpenquakeConfig | Path | None:
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


class HazardCurve(BaseModel):
    imts: list[str]
    imtls: list[float]


class HazardSite(BaseModel):
    # TODO: this is another swept argument used as a scalar in the task. Not sure how to fix h
    vs30: Optional[PositiveInt] = None
    locations: Optional[list[str]] = None
    locations_file: Optional[Path] = None
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
        if file_has_vs30 and self.vs30:
            raise ValueError("cannot specify both uniform and site-specific vs30")
        elif not file_has_vs30 and not self.vs30:
            raise ValueError("locations file must have vs30 column if uniform vs30 not given")

        return self


class OQHazardArgs(BaseModel):
    """Input for calculating hazard curves."""

    compatible_calc_id: Annotated[str, AfterValidator(is_compat_calc_id)]
    hazard_curve: HazardCurve
    filepath: FilePath
    hazard_model: HazardModel
    site_params: HazardSite


# Holding space for methods I may need later. Not sure where they go yet
class FooBar(BaseModel):

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
