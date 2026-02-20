"""This module provides the runner class for scaling the rupture rates of inversions."""

import runzi.tasks.scale_solution.scale_solution_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute import ArgSweeper
from runzi.tasks.time_dependent_solution.time_dependent_solution_runner import get_model_type_from_all
from runzi.tasks.toshi_utils import convert_gt_to_swept

from ...job_runner import JobRunner


class ScaleSolutionJobRunner(JobRunner):
    """A class to run scale solution jobs."""

    job_name = "Runzi-automation-scale-solution"
    subtask_type = SubtaskType.SCALE_SOLUTION

    def __init__(self, job_args: ArgSweeper):
        """Initialize the ScaleSolutionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.argument_sweeper)

    def get_model_type(self) -> ModelType:
        return get_model_type_from_all(self.argument_sweeper)
