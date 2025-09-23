"""This module provides the Pydantic class for defining inversion job inputs."""

from pydantic import BaseModel, field_validator, field_serializer, ValidationInfo, model_validator, Field, FilePath
from typing import Any, Optional, Generator
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType
from runzi.runners.runner_inputs import InputBase
from itertools import product


# TODO: typing sucks when all of these fields can be None. Can that be fixed w/o lots of cast or assert statements?
class InversionSystemArgs(BaseModel):
    java_gateway_port: Optional[int] = None
    working_path: Optional[FilePath] = None
    general_task_id: Optional[str] = None
    task_count: Optional[int] = None
    java_threads: Optional[int] = None
    java_gateway_port: Optional[int] = None
    opensha_root_folder: Optional[int] = None
    use_api: bool = False


class GeneralArgs(BaseModel):
    mock_mode: bool = False
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
    max_inversion_times: list[float]
    rupture_set_ids: list[str]
    threads_per_selectors: list[str]
    averaging_threads: list[str]
    initial_solution_ids: Optional[list[str]]

class OpenshaArgs(InputBase):
    # java: JavaArgs
    general: GeneralArgs

class InversionArgs(OpenshaArgs):
    task: TaskArgs

    def get_task_args(self) -> Generator['InversionArgs', None, None]:

        # empty/default entries can be anything
        names = self.task.model_fields_set
        values = [getattr(self.task, name) for name in names]
        for task_combination in product(*values):
            task_args = {name:[ta] for name, ta in zip(names, task_combination)}
            yield type(self)(**task_args)



    def get_run_args(self) -> dict:
        return self.task.model_dump()