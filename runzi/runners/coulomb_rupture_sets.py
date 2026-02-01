"""This module provides the runner class for creating Coulomb rupture sets."""

import runzi.execute.coulomb_rupture_set_builder_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import ArgSweeper

from .job_runner import JobRunner


class CoulombRuptureSetJobRunner(JobRunner):
    """A class to run Coulomb rupture set jobs."""

    job_name = "Runzi-automation-coulomb-rupture-sets"
    subtask_type = SubtaskType.RUPTURE_SET

    def __init__(self, job_args: ArgSweeper):
        """Initialize the CoulombRuptureSetJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def get_model_type(self) -> ModelType:
        """Get the model type for Coulomb rupture sets."""
        return ModelType.CRUSTAL
