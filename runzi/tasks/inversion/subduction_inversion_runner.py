"""This module provides the runner class for creating Coulomb rupture sets."""

import runzi.tasks.inversion.subduction_inversion_solution_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute import ArgSweeper

from ...job_runner import JobRunner


class SubductionInversionJobRunner(JobRunner):
    """A class to run subduction inversion jobs."""

    job_name = "Runzi-automation-subduction-inversion"
    subtask_type = SubtaskType.INVERSION

    def __init__(self, job_args: ArgSweeper):
        """Initialize the SubductionInversionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        """Get the model type for subduction inversion jobs."""
        return ModelType.SUBDUCTION
