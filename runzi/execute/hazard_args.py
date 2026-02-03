"""This module provides the Pydantic intput parameter classes of hazard and disaggregation caculations."""

from pathlib import Path
from typing import Any, Optional

from nzshm_model import all_model_versions
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    PositiveInt,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

try:
    from toshi_hazard_store.scripts.ths_import import chc_manager
except ImportError:
    print("openquake not installed, not importing toshi-hazard-store chc_manager")
from typing_extensions import Annotated, Self


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


class OQHazardArgs(BaseModel):
    """Input for calculating hazard curves."""

    compatible_calc_id: Annotated[str, AfterValidator(_is_compat_calc_id)]
    model_config = ConfigDict(arbitrary_types_allowed=True)
    nshm_model_version: Optional[str] = None
    srm_logic_tree: Optional[SourceLogicTree | Path] = None
    gmcm_logic_tree: Optional[GMCMLogicTree | Path] = None
    hazard_config: Optional[OpenquakeConfig | Path] = None
    imts: list[str]
    imtls: list[float]
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

    @field_validator('nshm_model_version', mode='after')
    @classmethod
    def is_model_version(cls, value: str | None) -> str | None:
        if (value is not None) and (value not in all_model_versions()):
            raise ValueError(f"must specify valid nshm_model_version ({all_model_versions()})")
        return value

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
