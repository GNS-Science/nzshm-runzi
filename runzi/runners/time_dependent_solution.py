"""This module provides the runner class for creating time dependent inversion solutions."""

import runzi.execute.time_dependent_solution_task as task_module
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage
from runzi.runners.utils import convert_gt_to_swept

from .runner import JobRunner
from .utils import toshi_api


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

    def __init__(self, job_args: ArgSweeper):
        """Initialize the TimeDependentSolutionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def custom_setup(self):
        self.system_args.task_language = TaskLanguage.JAVA
        self.system_args.java_threads = 16
        self.system_args.max_job_time_min = 60
        self.system_args.jvm_heap_max = 32
        self.system_args.job_name = "Runzi-automation-time-dependent-solution"
        self.system_args.subtask_type = SubtaskType.TIME_DEPENDENT_SOLUTION
        self.system_args.max_job_time_min = 10

        # convert GT IDs to swept IDs of inversion solutions
        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.job_args)

        # this has to be done after converting GT to inversion solution IDs
        self.system_args.model_type = get_model_type_from_all(self.job_args)
