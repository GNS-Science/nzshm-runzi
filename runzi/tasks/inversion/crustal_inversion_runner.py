"""This module provides the runner class for running crustal inversions."""

import runzi.tasks.inversion.crustal_inversion_solution_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.arguments import ArgSweeper

from runzi.job_runner import JobRunner


class CrustalInversionJobRunner(JobRunner):
    """A class to run Crustal inversion jobs."""

    subtask_type = SubtaskType.INVERSION
    job_name = "Runzi-automation-crustal-inversion"

    def __init__(self, job_args: ArgSweeper):
        """Initialize the CrustalInversionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        """Get the model type for Crustal inversion jobs."""
        return ModelType.CRUSTAL
