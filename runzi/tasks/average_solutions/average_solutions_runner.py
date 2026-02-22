"""This module provides the runner class for averaging the rupture rates from multiple inversions."""

import runzi.tasks.average_solutions.average_solutions_task as task_module
from runzi.arguments import ArgSweeper
from runzi.automation.task_utils import get_model_type
from runzi.automation.toshi_api import ModelType, SubtaskType
from runzi.job_runner import JobRunner
from runzi.tasks.toshi_utils import toshi_api


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

    job_name = "Runzi-automation-average-solutions"
    subtask_type = SubtaskType.AGGREGATE_SOLUTION

    def __init__(self, job_args: ArgSweeper):
        """Initialize the AverageSolutionsJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        """Get the model type from all source solution ids."""
        return get_model_type_from_all(self.argument_sweeper)
