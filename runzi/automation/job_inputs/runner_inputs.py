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
        config = tomlkit.parse(content).unwrap()
        return cls.model_validate(config)


class AverageSolutionsInput(InputBase):
    """Input for averaging solutions."""

    title: str
    description: str
    worker_pool_size: Optional[int] = None
    solution_groups: list[list[str]]
