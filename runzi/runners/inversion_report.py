"""This module provides the runner class for scaling the rupture rates of inversions."""

import runzi.execute.inversion_diags_report_task as task_module
from runzi.automation.scaling.local_config import BUILD_PLOTS, HACK_FAULT_MODEL, REPORT_LEVEL
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage
from runzi.runners.time_dependent_solution import get_model_type_from_all
from runzi.runners.utils import convert_gt_to_swept

from .runner import JobRunner


class InversionReportJobRunner(JobRunner):
    """A class to run inversion report."""

    job_name = "Runzi-automation-inversion-report"
    task_language = TaskLanguage.JAVA
    subtask_type = SubtaskType.REPORT

    java_threads = 16
    jvm_heap_max = 32

    ecs_max_job_time_min = 60
    ecs_memory = 30720
    ecs_vcpu = 4
    ecs_job_definition = "Fargate-runzi-opensha-JD"
    ecs_job_queue = "BasicFargate_Q"

    def __init__(self, job_args: ArgSweeper):
        """Initialize the InversionReportJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

        # convert GT IDs to swept IDs of inversion solutions
        convert_gt_to_swept(self.job_args)

        # set fields from env vars to replace dummy values set in the cli
        self.job_args.prototype.build_mfd_plots = BUILD_PLOTS
        self.job_args.prototype.build_report_level = REPORT_LEVEL
        self.job_args.prototype.hack_fault_model = HACK_FAULT_MODEL

    def get_model_type(self) -> ModelType:
        return get_model_type_from_all(self.job_args)
