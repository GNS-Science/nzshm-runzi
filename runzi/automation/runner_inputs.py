"""This module provides Pydantic classes for defining the inputs to jobs.

TOML files can be used to initialize the classes using the from_toml method.
"""

from pathlib import Path
from typing import Optional, TextIO

import tomlkit
from pydantic import BaseModel
from typing_extensions import Self


class InputBase(BaseModel):
    """Base class for input Pydantic classes."""

    worker_pool_size: Optional[int] = None
    title: str
    description: str

    @classmethod
    def from_toml(cls, toml_file: TextIO | Path | str) -> Self:
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
        return cls(**data)


class AverageSolutionsInput(InputBase):
    """Input for averaging solutions."""

    solution_groups: list[list[str]]

class AzimuthalRuptureSetsInput(InputBase):
    """"Input for generating azimuthal rupture sets."""

    models: list[str]
    strategies: list[str]
    jump_limits: list[float]
    ddw_ratios: list[float]
    min_sub_sects_per_parents: list[int]
    min_sub_sections_list: list[int]
    max_cumulative_azimuths: list[float]
    thinning_factors: list[float]
    scaling_relations: list[str]
    max_sections: int

class CoulombRuptureSetsInput(InputBase):
    """Input for generating Coulomb rupture sets."""

    class DepthScaling(BaseModel):
        tvz: float
        sans: float

    max_sections: int
    models: list[str]
    jump_limits: list[int]
    adaptive_min_distances: list[int]
    thinning_factors: list[float]
    min_sub_sects_per_parents: list[int]
    min_sub_sections_list: list[int]
    depth_scaling: list[DepthScaling]