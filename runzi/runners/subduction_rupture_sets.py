"""This module provides the runner class for creating subduction rupture sets."""

import runzi.execute.subduction_rupture_set_builder_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import TaskLanguage

from .runner import JobRunner


class SubductionRuptureSetJobRunner(JobRunner):
    """A class to run subduction rupture set jobs."""
    job_name = "Runzi-automation-coulomb-rupture-sets"
    subtask_type = SubtaskType.RUPTURE_SET
    task_language = TaskLanguage.JAVA

    java_threads = 16
    jvm_heap_max = 32

    ecs_max_job_time_min = 60
    ecs_memory = 30720
    ecs_vcpu = 4
    ecs_job_definition = "Fargate-runzi-opensha-JD"
    ecs_job_queue = "BasicFargate_Q"

    def __init__(self, job_args):
        """Initialize the SubductionRuptureSetJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        return ModelType.SUBDUCTION