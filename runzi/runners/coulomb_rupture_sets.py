"""This module provides the runner class for creating Coulomb rupture sets."""

import runzi.execute.coulomb_rupture_set_builder_task as task_module
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage

from .runner import JobRunner


class CoulombRuptureSetJobRunner(JobRunner):
    """A class to run Coulomb rupture set jobs."""

    def __init__(self, job_args: ArgSweeper):
        """Initialize the CoulombRuptureSetJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def custom_setup(self):
        self.system_args.task_language = TaskLanguage.JAVA
        self.system_args.java_threads = 16
        self.system_args.ecs_max_job_time_min = 60
        self.system_args.jvm_heap_max = 32
        self.system_args.job_name = "Runzi-automation-coulomb-rupture-sets"
        self.system_args.subtask_type = SubtaskType.RUPTURE_SET
        self.system_args.model_type = ModelType.CRUSTAL
