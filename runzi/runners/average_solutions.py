"""This module provides the runner class for averaging the rupture rates from multiple inversions."""

import runzi.execute.average_solutions_task as task_module
from runzi.automation.scaling.local_config import API_KEY, API_URL
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType, ToshiApi
from runzi.execute.arguments import ArgSweeper, TaskLanguage

from .utils import toshi_api

from .runner import JobRunner


def get_model_type_from_all(job_args: ArgSweeper) -> ModelType:
    model_type = None
    for task_args in job_args.get_tasks():
        new_model_type = get_model_type(task_args.source_solution_ids, toshi_api)  # type: ignore
        if not model_type:
            model_type = new_model_type
        else:
            if new_model_type is model_type:
                continue
            else:
                raise Exception('model types are not all the same for all source solution ids')
    if model_type is None:
        raise Exception("Could not find model type.")
    return model_type


class AverageSolutionsJobRunner(JobRunner):
    """A class to run average solutions jobs."""

    def __init__(self, job_args: ArgSweeper):
        """Initialize the AverageSolutionsJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def custom_setup(self):
        self.system_args.task_language = TaskLanguage.PYTHON
        self.system_args.job_name = "Runzi-automation-average-solutions"
        self.system_args.subtask_type = SubtaskType.AGGREGATE_SOLUTION
        self.system_args.model_type = get_model_type_from_all(self.job_args)
        self.system_args.max_job_time_min = 10
