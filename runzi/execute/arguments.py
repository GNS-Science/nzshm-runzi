import json
from enum import Enum
from pathlib import Path
from tkinter import NO
from typing import Any, Generator, Optional, Sequence, TextIO

import tomlkit
from pydantic import BaseModel
from typing_extensions import Self

from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.util.aws import BatchEnvironmentSetting


class TaskLanguage(Enum):
    PYTHON = 'python'
    JAVA = 'java'


class SystemArgs(BaseModel):

    job_name: str
    task_language: TaskLanguage
    subtask_type: SubtaskType
    general_task_id: Optional[str]
    task_count: int = 0
    use_api: bool

    java_threads: Optional[int] = None
    jvm_heap_max: Optional[int] = None
    java_gateway_port: Optional[int] = None

    ecs_max_job_time_min: int
    ecs_memory: int
    ecs_vcpu: int
    ecs_job_definition: str
    ecs_job_queue: str
    ecs_extra_env: Optional[list[BatchEnvironmentSetting]] = None





class ArgBase(BaseModel):
    """Base class for job arguments."""

    # TODO: remove me?
    @classmethod
    def from_toml_file(cls, toml_file: TextIO | Path | str) -> Self:
        """Creates a job argument object from a toml file.

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

    # TODO: remove me?
    @classmethod
    def from_json_file(cls, json_file: TextIO | Path | str) -> Self:
        """Creates a job argument object from a json file.

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

    def get_run_args(self) -> dict[str, Any]:
        """Get a dictionary of argument names to values for use in Toshi API.

        Will include all arguments, excluding title and description.

        Returns:
            A dictionary of argument names to values.
        """
        return self.model_dump()


class ArgSweeper:
    """Class to hold argument prototype and swept arguments."""

    def __init__(self, prototype: ArgBase, swept_args: dict[str, Sequence[Any]], title: str, description: str):
        """Initialize a SweptArgs instance.

        Args:
            prototype: The prototype job argument object.
            swept_args: A dictionary of argument names to lists of values to be swept.
            title: The title for the job.
            description: The description for the job.
        """

        self.prototype = prototype
        self.swept_args = swept_args
        self.title = title
        self.description = description

    # TODO: remove me?
    def get_run_args(self) -> dict[str, Any]:
        """Get a dictionary of argument names to lists of values for use in Toshi API.

        Returns:
            A dictionary of argument names to lists of values.
        """
        return self.prototype.get_run_args() | self.swept_args

    @classmethod
    def from_config_file(cls, config_file: TextIO | Path | str, config_type: type[ArgBase]) -> Self:
        """Create a prototype job argument object and a dict of arguments to be swept.

        Config files are json format and can optionally contain a "swept_args" object that specifies the names and
        list of values for an argument to take in the jobs to be created.  The prototype object is generated from the
        first value from each of the swept arguments. The dict keys are the argument names and values are lists of
        argument values.

        Args:
            config_file: File-like object or path to configuration file.
            config_type: The type of the configuration object.

        Returns:
            A tuple of the prototype config object and a dictionary of arguments to be swept.
        """

        if isinstance(config_file, (Path, str)):
            json_str = Path(config_file).read_text()
        else:
            json_str = config_file.read()

        data = json.loads(json_str)
        title = data.pop("title")
        description = data.pop("description")
        swept_args = data.pop("swept_args", {})

        if swept_args:
            for k, v in swept_args.items():
                if k in data:
                    raise ValueError(f"Swept argument '{k}' also specified in unswept arguments")
                if not all(isinstance(item, type(v[0])) for item in v):
                    raise ValueError(f"All values for swept argument '{k}' must be of the same type")
                data[k] = v[0]
        prototype = config_type.model_validate(data, extra='forbid')

        return cls(prototype, swept_args, title, description)

    def get_tasks(self) -> Generator[ArgBase, None, None]:
        """Generate all combinations of swept arguments as job argument objects.

        Yields:
            Job argument objects for each combination of swept arguments.
        """
        from itertools import product

        if not self.swept_args:
            yield self.prototype
            return

        prototype_data = self.prototype.model_dump()
        for values in product(*self.swept_args.values()):
            update_data = dict(zip(self.swept_args.keys(), values))
            yield self.prototype.model_validate(prototype_data | update_data)
