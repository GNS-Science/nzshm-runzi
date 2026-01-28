"""This module provides the runner class for scaling the rupture rates of inversions."""

import runzi.execute.scale_solution_task as task_module
from runzi.automation.scaling.toshi_api import SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage
from runzi.runners.time_dependent_solution import get_model_type_from_all
from runzi.runners.utils import convert_gt_to_swept, get_solution_ids_from_id

from .runner import JobRunner


class ScaleSolutionJobRunner(JobRunner):
    """A class to run scale solution jobs."""

    def __init__(self, job_args: ArgSweeper):
        """Initialize the ScaleSolutionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def custom_setup(self):
        self.system_args.task_language = TaskLanguage.PYTHON
        self.system_args.job_name = "Runzi-automation-scale-solution"
        self.system_args.subtask_type = SubtaskType.SCALE_SOLUTION
        self.system_args.max_job_time_min = 10

        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.job_args)

        # this has to be done after converting GT to inversion solution IDs
        self.system_args.model_type = get_model_type_from_all(self.job_args)
