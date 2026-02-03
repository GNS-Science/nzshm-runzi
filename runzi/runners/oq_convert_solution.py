"""This module provides the runner class for OQ conversion of OpenSHA inversions."""

import runzi.execute.oq_opensha_convert_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute import ArgSweeper
from runzi.runners.time_dependent_solution import get_model_type_from_all
from runzi.runners.utils import convert_gt_to_swept

from .job_runner import JobRunner


class OQConvertJobRunner(JobRunner):
    """A class to run OQ convert solution jobs."""

    job_name = "Runzi-automation-convert-solution"
    subtask_type = SubtaskType.SOLUTION_TO_NRML

    def __init__(self, job_args: ArgSweeper):
        """Initialize the OQConvertJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.argument_sweeper)

    def get_model_type(self) -> ModelType:
        # this has to be done after converting GT to inversion solution IDs
        return get_model_type_from_all(self.argument_sweeper)
