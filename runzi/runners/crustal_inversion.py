"""This module provides the runner class for creating Coulomb rupture sets."""

import runzi.execute.crustal_inversion_solution_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage

from .runner import JobRunner


class CrustalInversionJobRunner(JobRunner):
    """A class to run Crustal inversion jobs."""

    job_name = "Runzi-automation-crustal-inversion"
    task_language = TaskLanguage.JAVA
    subtask_type = SubtaskType.INVERSION

    # java_threads is only used for pbs mode, which is not supported anymore.
    # It should be set to selector_threads * averaging_threads, but this would need to be done task by task if they
    # are swept args. It would be possible to add some inversion specific code to the build_tasks function or find the
    # maximum number of threads before hand or find the maximum number of threads that would be needed before hand.
    java_threads = 16
    jvm_heap_max = 32

    ecs_max_job_time_min = 60
    ecs_memory = 30720
    ecs_vcpu = 4
    ecs_job_definition = "Fargate-runzi-opensha-JD"
    ecs_job_queue = "BasicFargate_Q"

    def __init__(self, job_args: ArgSweeper):
        """Initialize the CrustalInversionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        """Get the model type for Crustal inversion jobs."""
        return ModelType.CRUSTAL
