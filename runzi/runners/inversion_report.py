"""This module provides the runner class for scaling the rupture rates of inversions."""

from typing import cast

import runzi.execute.inversion_diags_report_task as task_module
from runzi.automation.scaling.local_config import BUILD_PLOTS, HACK_FAULT_MODEL, REPORT_LEVEL
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute import ArgSweeper
from runzi.execute.inversion_diags_report_task import InversionReportArgs
from runzi.runners.time_dependent_solution import get_model_type_from_all
from runzi.runners.utils import convert_gt_to_swept

from .job_runner import JobRunner


class InversionReportJobRunner(JobRunner):
    """A class to run inversion report."""

    job_name = "Runzi-automation-inversion-report"
    subtask_type = SubtaskType.REPORT

    def __init__(self, job_args: ArgSweeper):
        """Initialize the InversionReportJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)
        self.argument_sweeper.prototype_args = cast(InversionReportArgs, self.argument_sweeper.prototype_args)

        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.argument_sweeper)

        # set fields from env vars to replace dummy values set in the cli
        self.argument_sweeper.prototype_args.build_mfd_plots = BUILD_PLOTS
        self.argument_sweeper.prototype_args.build_report_level = REPORT_LEVEL
        self.argument_sweeper.prototype_args.hack_fault_model = HACK_FAULT_MODEL

    def get_model_type(self) -> ModelType:
        return get_model_type_from_all(self.argument_sweeper)
