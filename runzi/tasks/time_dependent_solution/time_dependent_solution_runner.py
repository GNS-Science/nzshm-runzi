"""This module provides the runner class for creating time dependent inversion solutions."""

import runzi.tasks.time_dependent_solution.time_dependent_solution_task as task_module
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute import ArgSweeper
from runzi.tasks.toshi_utils import convert_gt_to_swept

from ...job_runner import JobRunner
from ..toshi_utils import toshi_api


# TODO: redundant code shared by average_solutions, but just enough difference to need a new function. Can we merge?
def get_model_type_from_all(job_args: ArgSweeper) -> ModelType:
    model_type = None
    for task_args in job_args.get_tasks():
        new_model_type = get_model_type([task_args.source_solution_id], toshi_api)  # type: ignore
        if not model_type:
            model_type = new_model_type
        else:
            if new_model_type is model_type:
                continue
            else:
                raise Exception('model types are not all the same for all source solution ids')
    if model_type is None:
        raise Exception("Could not get model type.")
    return model_type


class TimeDependentSolutionJobRunner(JobRunner):
    """A class to run time dependent solution jobs."""

    job_name = "Runzi-automation-time-dependent-solution"
    subtask_type = SubtaskType.TIME_DEPENDENT_SOLUTION

    def __init__(self, job_args: ArgSweeper):
        """Initialize the TimeDependentSolutionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)
        convert_gt_to_swept(self.argument_sweeper)

    def get_model_type(self) -> ModelType:
        return get_model_type_from_all(self.argument_sweeper)
