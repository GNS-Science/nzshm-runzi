from pathlib import Path
from typing import Any, Optional, Union
from typing_extensions import Annotated

from nzshm_model import all_model_versions
from toshi_hazard_store.model import AggregationEnum
from pydantic import BaseModel, FilePath, PositiveInt, ValidationInfo, field_validator, model_validator, AfterValidator, BeforeValidator
from typing_extensions import Self


def is_model_version(value: str) -> str:
    if value not in all_model_versions():
        raise ValueError("must specify valid nshm_model_version ({})".format(all_model_versions()))
    return value
    
def resolve_path(path: Union[Path, str], reference_filepath: Union[Path, str]) -> str:
    path = Path(path)
    if not path.is_absolute():
        return str(Path(reference_filepath).parent / path)
    return str(path)


def coerce_to_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return [value]
    return value


class GeneralConfig(BaseModel):
    title: str
    description: str = ''




class HazardModelConfig(BaseModel):
    nshm_model_version: Annotated[Optional[str], AfterValidator(is_model_version)] = None
    srm_logic_tree: Optional[FilePath] = None
    gmcm_logic_tree: Optional[FilePath] = None
    hazard_config: Optional[FilePath] = None

    @model_validator(mode='after')
    def check_logic_trees(self) -> Self:
        if not self.nshm_model_version and not (self.srm_logic_tree and self.gmcm_logic_tree and self.hazard_config):
            raise ValueError(
                """if nshm_model_version not specified, must provide all of
                gmcm_logic_tree, srm_logic_tree, and hazard_config file paths"""
            )
        return self



class CalculationConfig(BaseModel):
    num_workers: PositiveInt = 1


class HazardCurveConfig(BaseModel):
    imts: Annotated[list[str], BeforeValidator(coerce_to_list)]
    imtls: Annotated[list[float], BeforeValidator(coerce_to_list)]


class HazardSiteConfig(BaseModel):
    vs30s: Annotated[Optional[list[PositiveInt]], BeforeValidator(coerce_to_list)] = None
    locations: Annotated[Optional[list[str]], BeforeValidator(coerce_to_list)] = None
    locations_file: Optional[FilePath] = None

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

        file_has_vs30 = self.locations_file and self.has_vs30(self.locations_file)
        if file_has_vs30 and self.vs30s:
            raise ValueError("cannot specify both uniform and site-specific vs30")
        elif not file_has_vs30 and not self.vs30s:
            raise ValueError("locations file must have vs30 column if uniform vs30 not given")

        return self


class HazardConfig(BaseModel):
    filepath: FilePath
    general: GeneralConfig
    hazard_model: HazardModelConfig
    calculation: CalculationConfig
    hazard_curve: HazardCurveConfig
    site_params: HazardSiteConfig


    # resolve absolute paths (relative to input file) for optional logic tree and config fields
    @field_validator('hazard_model', mode='before')
    @classmethod
    def absolute_model_paths(cls, data: Any, info: ValidationInfo) -> Any:
        if isinstance(data, dict):
            for key in ["srm_logic_tree", "gmcm_logic_tree", "hazard_config"]:
                if data.get(key):
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


class DisaggCurveConfig(BaseModel):
    hazard_model_id: Annotated[str, AfterValidator(is_model_version)]
    aggs: Annotated[list[AggregationEnum], BeforeValidator(coerce_to_list)]
    imts: Annotated[list[str], BeforeValidator(coerce_to_list)]



class DisaggProbConfig(BaseModel):
    inv_time: int
    poes: Annotated[list[float], BeforeValidator(coerce_to_list)]

class DisaggOutput(BaseModel):
    gt_filename: str

class DisaggConfig(BaseModel):
    filepath: FilePath
    general: GeneralConfig
    hazard_model: HazardModelConfig
    hazard_curve: DisaggCurveConfig
    site_params: HazardSiteConfig
    disagg: DisaggProbConfig
    calculation: CalculationConfig
    output: DisaggOutput

