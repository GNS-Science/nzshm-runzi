"""This module provides the runner class for scaling the rupture rates of inversions."""

from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
import runzi.execute.inversion_diags_report_task as task_module
from runzi.execute.arguments import ArgSweeper, TaskLanguage
from runzi.runners.utils import convert_gt_to_swept
from runzi.runners.time_dependent_solution import get_model_type_from_all
from runzi.automation.scaling.local_config import REPORT_LEVEL, BUILD_PLOTS, HACK_FAULT_MODEL

from .runner import JobRunner

class InversionReportJobRunner(JobRunner):
    """A class to run inversion report."""

    def __init__(self, job_args: ArgSweeper):
        """Initialize the InversionReportJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def custom_setup(self):
        self.system_args.job_name = "Runzi-automation-inversion-report"
        self.system_args.task_language = TaskLanguage.JAVA
        self.system_args.java_threads = 16
        self.system_args.max_job_time_min = 60
        self.system_args.jvm_heap_max = 32
        self.system_args.job_name = "Runzi-automation-coulomb-rupture-sets"
        self.system_args.subtask_type = SubtaskType.REPORT

        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.job_args)

        # set fields from env vars to replace dummy values set in the cli
        self.job_args.prototype.build_mfd_plots = BUILD_PLOTS
        self.job_args.prototype.build_report_level=REPORT_LEVEL
        self.job_args.prototype.hack_fault_model = HACK_FAULT_MODEL

        # this has to be done after converting GT to inversion solution IDs
        self.system_args.model_type = get_model_type_from_all(self.job_args)