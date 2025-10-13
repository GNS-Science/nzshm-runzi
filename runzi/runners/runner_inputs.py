"""This module provides the base Pydantic class for defining the inputs to jobs.

TOML files can be used to initialize the classes using the from_toml method.
"""

from pathlib import Path
from typing import Any, Optional, TextIO

import tomlkit
from pydantic import BaseModel, field_validator
from typing_extensions import Self

from runzi.automation.scaling.toshi_api import ModelType


class InputBase(BaseModel):
    """Base class for input Pydantic classes."""

    # TODO: should we have a worker size or only use env? Need to be consistent
    # worker_pool_size: int = 1
    title: str
    description: str

    @classmethod
    def from_toml_file(cls, toml_file: TextIO | Path | str) -> Self:
        """Creates an input object from a toml file.

        Args:
            toml_file: File-like object or path to TOML file.

        Returns:
            An instance of the class initialized with the TOML file.
        """
        if isinstance(toml_file, (Path, str)):
            with Path(toml_file).open() as f:
                content = f.read()
        else:
            content = toml_file.read()
        data = tomlkit.parse(content).unwrap()
        return cls.model_validate(data, extra='forbid')

    @classmethod
    def from_json_file(cls, json_file: TextIO | Path | str) -> Self:
        """Creates an input object from a json file.

        Args:
            toml_file: File-like object or path to TOML file.

        Returns:
            An instance of the class initialized with the TOML file.
        """
        if isinstance(json_file, (Path, str)):
            with Path(json_file).open() as f:
                content = f.read()
        else:
            content = json_file.read()
        return cls.model_validate_json(content, extra='forbid')

    def to_json_file(self, json_file: TextIO | Path | str):
        """Serializes the input object to a JSON file.

        Args:
            json_file: File-like object or path to file to be written.
        """
        json_str = self.model_dump_json(indent=4)
        if isinstance(json_file, (Path, str)):
            Path(json_file).write_text(json_str)
        else:
            json_file.write(json_str)


class InversionReportArgs(BaseModel):
    solution_id: str
    build_mfd_plots: bool
    build_report_level: str | None
    fault_model: str | None
    general_task_id: str


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


class OQOpenSHAConvertArgs(InputBase):
    task: OQOpenSHAConvertTaskArgs

    def get_run_args(self) -> dict:
        return self.task.model_dump(mode='json')


class AverageSolutionsInput(InputBase):
    """Input for averaging solutions."""

    solution_groups: list[list[str]]
    model_type: Optional[ModelType] = None


class SystemArgs(BaseModel):
    java_gateway_port: int = 0
    general_task_id: Optional[str] = None
    task_count: int = 0
    java_threads: int = 0
    use_api: bool = False
