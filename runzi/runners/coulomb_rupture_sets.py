"""This module provides the runner class for creating Coulomb rupture sets."""

import runzi.execute.coulomb_rupture_set_builder_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage

from .runner import JobRunner


class CoulombRuptureSetJobRunner(JobRunner):
    """A class to run Coulomb rupture set jobs."""

    job_name = "Runzi-automation-coulomb-rupture-sets"
    task_language = TaskLanguage.JAVA
    subtask_type = SubtaskType.RUPTURE_SET

    java_threads = 16
    jvm_heap_max = 32

    ecs_max_job_time_min = 60
    ecs_memory = 30720
    ecs_vcpu = 4
    ecs_job_definition = "Fargate-runzi-opensha-JD"
    ecs_job_queue = "BasicFargate_Q"

    def __init__(self, job_args: ArgSweeper):
        """Initialize the CoulombRuptureSetJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        """Get the model type for Coulomb rupture sets."""
        return ModelType.CRUSTAL
