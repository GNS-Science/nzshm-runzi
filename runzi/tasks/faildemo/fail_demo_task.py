"""A deliberately-failing diagnostic task.

Its only job is to exit with a non-zero status so we can confirm end-to-end that AWS Batch reports
FAILED (not SUCCEEDED) for a failed job — the regression guarded by issue #333.

It is declared as a ``TaskLanguage.JAVA`` task on purpose: the exit-code masking bug lived only in the
Java container launcher (``docker/java_container_task.sh``), so the demo must route through that path
(via ``OpenshaAWSTaskFactory``) to be a meaningful real-world test. The JVM gateway starting or not is
irrelevant — only the python exit status matters.
"""

import sys

from pydantic import BaseModel

from runzi.arguments import SubmissionArgs, TaskLanguage
from runzi.tasks.get_config import get_config

default_submission_args = SubmissionArgs(
    task_language=TaskLanguage.JAVA,
    ecs_max_job_time_min=5,
    ecs_memory=2048,
    ecs_vcpu=1,
)


class FailDemoArgs(BaseModel):
    """Input for the intentional-failure diagnostic task."""

    exit_code: int = 1
    """Non-zero status the task exits with (AWS Batch should surface this as FAILED)."""

    message: str = "intentional failure for issue #333 batch-fail-signal test"
    """Marker line printed before exiting, to make the job's logs unambiguous."""


if __name__ == "__main__":
    config = get_config()
    user_args = FailDemoArgs(**config.get('task_args', {}))
    print(f"[fail-demo] {user_args.message}; exiting {user_args.exit_code}", flush=True)
    sys.exit(user_args.exit_code)
