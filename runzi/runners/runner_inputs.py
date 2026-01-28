"""This module provides the base Pydantic class for defining the inputs to jobs.

TOML files can be used to initialize the classes using the from_toml method.
"""

from typing import Any, Optional

from pydantic import BaseModel, field_validator

from runzi.automation.scaling.toshi_api import ModelType
from runzi.execute.arguments import ArgBase


class OQOpenSHAConvertTaskArgs(BaseModel):
    """Input for OpenSHA to OpenQuake conversion."""

    source_solution_id: str
    investigation_time_years: float
    model_type: ModelType
    rupture_sampling_distance_km: float

    @field_validator('model_type', mode='before')
    @classmethod
    def _convert_to_enum(cls, value: Any) -> ModelType:
        if isinstance(value, ModelType):
            return value
        try:
            return ModelType[value.upper()]
        except (KeyError, AttributeError):
            try:
                return ModelType(value)
            except ValueError:
                raise ValueError("model_type input is not valid")


class OQOpenSHAConvertArgs(ArgBase):
    task: OQOpenSHAConvertTaskArgs

    def get_run_args(self) -> dict:
        return self.task.model_dump(mode='json')


class AverageSolutionsInput(ArgBase):
    """Input for averaging solutions."""

    solution_groups: list[list[str]]
    model_type: Optional[ModelType] = None
