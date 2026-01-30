"""This module provides the runner class for scaling the rupture rates of inversions."""

import runzi.execute.scale_solution_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage
from runzi.runners.time_dependent_solution import get_model_type_from_all
from runzi.runners.utils import convert_gt_to_swept

from .runner import JobRunner


class ScaleSolutionJobRunner(JobRunner):
    """A class to run scale solution jobs."""

    job_name = "Runzi-automation-scale-solution"
    task_language = TaskLanguage.PYTHON
    subtask_type = SubtaskType.SCALE_SOLUTION

    ecs_max_job_time_min = 10
    ecs_memory = 30720
    ecs_vcpu = 4
    ecs_job_definition = "Fargate-runzi-opensha-JD"
    ecs_job_queue = "BasicFargate_Q"

    def __init__(self, job_args: ArgSweeper):
        """Initialize the ScaleSolutionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.job_args)

    def get_model_type(self) -> ModelType:
        return get_model_type_from_all(self.job_args)
