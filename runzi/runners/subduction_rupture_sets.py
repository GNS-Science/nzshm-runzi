"""This module provides the runner class for creating subduction rupture sets."""

import runzi.execute.subduction_rupture_set_builder_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType

from .job_runner import JobRunner


class SubductionRuptureSetJobRunner(JobRunner):
    """A class to run subduction rupture set jobs."""

    job_name = "Runzi-automation-coulomb-rupture-sets"
    subtask_type = SubtaskType.RUPTURE_SET

    def __init__(self, job_args):
        """Initialize the SubductionRuptureSetJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        return ModelType.SUBDUCTION
