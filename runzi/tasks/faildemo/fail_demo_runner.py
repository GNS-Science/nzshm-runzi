"""Runner for the intentional-failure diagnostic task (issue #333)."""

import runzi.tasks.faildemo.fail_demo_task as task_module
from runzi.arguments import ArgSweeper
from runzi.automation.toshi_api import ModelType, SubtaskType
from runzi.job_runner import JobRunner


class FailDemoJobRunner(JobRunner):
    """Submit a task that deliberately exits non-zero, to verify Batch failure signalling."""

    job_name = "Runzi-automation-fail-demo"
    # Reuse an existing toshi subtask_type: the API rejects unknown values, and this diagnostic
    # is a throwaway anyway (typically run with the API disabled). INVERSION is a harmless label.
    subtask_type = SubtaskType.INVERSION

    def __init__(self, job_args: ArgSweeper):
        """Initialize the FailDemoJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)  # type: ignore

    def get_model_type(self) -> ModelType:
        # Arbitrary; only used to tag the general task when the toshi API is enabled.
        return ModelType.CRUSTAL
