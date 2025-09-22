"""This module provides the Pydantic class for defining inversion job inputs."""

from pydantic import BaseModel, field_validator, field_serializer, ValidationInfo, model_validator, Field, FilePath
from typing import Any, Optional, Generator
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType
from runzi.runners.runner_inputs import InputBase
from itertools import product


class SystemInversionArgs(BaseModel):
    java_gateway_port: int
    working_path: FilePath


class GeneralArgs(BaseModel):
    mock_mode: bool = False
    use_api: bool = False
    general_task_id: str
    unique_id: Optional[str] = None
    title: str
    description: str
    subtask_type: SubtaskType
    model_type: ModelType
    worker_pool_size: int
    jvm_heap_max: int
    java_threads: int
    root_folder: FilePath

class TaskArgs(BaseModel):
    max_inversion_times: Optional[list[float]] = None
    rupture_set_ids: list[str]
    threads_per_selectors: list[str]
    averaging_threads: list[str]

class OpenshaArgs(InputBase):
    # java: JavaArgs
    general: GeneralArgs

class InversionArgs(OpenshaArgs):
    task: TaskArgs

    def get_task_inputs(self) -> Generator['InversionArgs', None, None]:

        # empty/default entries can be anything
        names = self.task.model_fields_set
        values = [getattr(self.task, name) for name in names]
        for task_combination in product(*values):
            task_args = {name:[ta] for name, ta in zip(names, task_combination)}
            yield type(self)(task_args)



    def get_run_args(self) -> dict:
        return self.inversion.model_dump()