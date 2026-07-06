import copy
import json
import os
from collections.abc import Generator, Sequence
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple, Self

from pydantic import BaseModel

from runzi.aws import BatchEnvironmentSetting


class TaskLanguage(Enum):
    PYTHON = 'python'
    JAVA = 'java'


class ComputeEnvironment(Enum):
    """Which AWS Batch compute target a job runs on.

    Fargate is the default for every task; EC2 is an explicit per-job opt-in (set via a config
    file's submission_arg_overrides) for jobs that need a size or instance feature Fargate can't
    provide. See docs/usage/aws_batch.md.
    """

    FARGATE = 'fargate'
    EC2 = 'ec2'


# Canonical AWS Batch compute targets. All tasks default to a single Fargate compute environment and
# queue (see docs/architecture/adr/0003-aws-batch-compute-consolidation.md). The job definitions are
# Terraform-owned and track stable image tags (:prod / :experimental); the default resolves to the
# prod definition. Override ecs_job_definition (e.g. via submission_arg_overrides) with
# EXPERIMENTAL_JOB_DEFINITION to run the experimental image
# (see docs/architecture/adr/0007-job-definition-terraform-tag-publish.md).
DEFAULT_JOB_DEFINITION = "runzi-fargate-JD"
EXPERIMENTAL_JOB_DEFINITION = "runzi-fargate-experimental-JD"
DEFAULT_JOB_QUEUE = "BasicFargate_Q"

# The EC2 compute target mirrors Fargate for jobs that opt in via submission_arg_overrides
# (ecs_compute_environment: ec2, plus ecs_job_queue / ecs_job_definition set to the EC2 names
# below). One On-Demand EC2 compute environment + queue + two Terraform-owned job definitions that
# track the same :prod / :experimental tags as their Fargate counterparts
# (see docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md).
EC2_JOB_DEFINITION = "runzi-ec2-JD"
EC2_EXPERIMENTAL_JOB_DEFINITION = "runzi-ec2-experimental-JD"
EC2_JOB_QUEUE = "runzi-ec2-Q"


class BatchTarget(NamedTuple):
    """The job queue and compute-environment type a given job definition must run on."""

    job_queue: str
    compute_environment: ComputeEnvironment


# Each canonical job definition has exactly one correct queue + compute-environment type, so a user
# only needs to pick the job definition; the queue and type are derived from it (see
# SubmissionArgs.resolved_job_queue / resolved_compute_environment). An unknown/custom job definition
# falls back to DEFAULT_BATCH_TARGET (Fargate), so behaviour is unchanged unless a config explicitly
# sets ecs_job_queue / ecs_compute_environment.
JOB_DEFINITION_TARGETS: dict[str, BatchTarget] = {
    DEFAULT_JOB_DEFINITION: BatchTarget(DEFAULT_JOB_QUEUE, ComputeEnvironment.FARGATE),
    EXPERIMENTAL_JOB_DEFINITION: BatchTarget(DEFAULT_JOB_QUEUE, ComputeEnvironment.FARGATE),
    EC2_JOB_DEFINITION: BatchTarget(EC2_JOB_QUEUE, ComputeEnvironment.EC2),
    EC2_EXPERIMENTAL_JOB_DEFINITION: BatchTarget(EC2_JOB_QUEUE, ComputeEnvironment.EC2),
}
DEFAULT_BATCH_TARGET = BatchTarget(DEFAULT_JOB_QUEUE, ComputeEnvironment.FARGATE)


class SubmissionArgs(BaseModel):
    """Config the local submitter uses to shape and submit the AWS Batch job.

    Declared per task module (see each module's ``default_submission_args``) and read only on the
    submitter side (build_tasks / job_runner / the task factories / get_ecs_job_config). It is NOT
    serialized to the worker — the worker gets a TaskRuntimeArgs instead. Splitting these apart keeps
    submission-only fields out of the worker's validation surface (see
    docs/architecture/adr/0009-submission-vs-runtime-args.md).
    """

    task_language: TaskLanguage

    # Declared per Java task module; the worker reads it, so build_tasks copies it into TaskRuntimeArgs.
    java_threads: int | None = None
    jvm_heap_max: int | None = None

    ecs_max_job_time_min: int
    ecs_memory: int
    ecs_vcpu: int
    ecs_job_definition: str = DEFAULT_JOB_DEFINITION
    # None on ecs_job_queue / ecs_compute_environment means "derive from ecs_job_definition"; set
    # explicitly (e.g. via submission_arg_overrides) only to override the queue/compute-environment the job
    # definition would otherwise select. Read the resolved values via resolved_job_queue /
    # resolved_compute_environment. (submission_arg_overrides' setattr path can leave a raw string on
    # ecs_compute_environment; resolved_compute_environment and get_ecs_job_config tolerate that.)
    ecs_job_queue: str | None = None
    ecs_compute_environment: ComputeEnvironment | None = None
    ecs_extra_env: list[BatchEnvironmentSetting] | None = None

    @property
    def resolved_job_queue(self) -> str:
        """The job queue to submit to: the explicit override, else the one the job definition selects."""
        if self.ecs_job_queue is not None:
            return self.ecs_job_queue
        return JOB_DEFINITION_TARGETS.get(self.ecs_job_definition, DEFAULT_BATCH_TARGET).job_queue

    @property
    def resolved_compute_environment(self) -> 'ComputeEnvironment | str':
        """The compute-environment type: the explicit override, else the one the job definition selects.

        May be a raw string when set via submission_arg_overrides' setattr path (which bypasses pydantic
        coercion); get_ecs_job_config tolerates both the enum and the string.
        """
        if self.ecs_compute_environment is not None:
            return self.ecs_compute_environment
        return JOB_DEFINITION_TARGETS.get(self.ecs_job_definition, DEFAULT_BATCH_TARGET).compute_environment


class TaskRuntimeArgs(BaseModel):
    """Per-task context the worker needs at execution time.

    Assembled by the submitter (build_tasks) and serialized to the worker under the
    ``task_runtime_args`` config key; the worker rebuilds it in each task module's ``__main__``. This
    is the only args model that crosses the submitter->worker boundary, so it must stay small and
    evolve compatibly with deployed images (see docs/architecture/adr/0009-submission-vs-runtime-args.md).
    """

    general_task_id: str | None = None
    task_count: int = 0
    use_api: bool
    java_threads: int | None = None

    @property
    def java_gateway_port(self) -> int:
        """The py4j gateway port, read from NZSHM22_APP_PORT at runtime.

        The port belongs to the JVM process, not the submitter: whichever launcher starts the
        gateway exports NZSHM22_APP_PORT (a free port per container on AWS Batch, where forced host
        networking makes a fixed port collide across concurrent jobs; the per-task port in the
        generated bash script on LOCAL/CLUSTER). Reading it here — rather than shipping it in the
        config — keeps the JVM and the Python client on the same port with a single source of truth.
        """
        port = os.environ.get('NZSHM22_APP_PORT')
        if port is None:
            raise RuntimeError(
                "NZSHM22_APP_PORT is not set; the task launcher must export it before the JVM gateway starts"
            )
        return int(port)


class ArgSweeper:
    """Class to hold argument prototype and swept arguments."""

    def __init__(
        self,
        prototype_args: BaseModel,
        swept_args: dict[str, Sequence[Any]],
        title: str,
        description: str,
        submission_arg_overrides: dict[str, Any] | None = None,
    ):
        """Initialize a SweptArgs instance.

        Args:
            prototype: The prototype job argument object.
            swept_args: A dictionary of argument names to lists of values to be swept.
            title: The title for the job.
            description: The description for the job.
            submission_arg_overrides: SubmissionArgs fields to override from the JobRunner default.
        """

        self.prototype_args = prototype_args
        self.swept_args = swept_args
        self.title = title
        self.description = description
        self.submission_arg_overrides = submission_arg_overrides or {}

    @classmethod
    def from_config_file(cls, config_file: Path | str, args_class: type[BaseModel]) -> Self:
        """Create a prototype job argument object and a dict of arguments to be swept.

        Config files are json format and can optionally contain a "swept_args" object that specifies the names and
        list of values for an argument to take in the jobs to be created.  The prototype object is generated from the
        first value from each of the swept arguments. The dict keys are the argument names and values are lists of
        argument values.

        Args:
            config_file: File-like object or path to configuration file.
            args_class: The type (class) of the configuration/arguments object.

        Returns:
            A tuple of the prototype config object and a dictionary of arguments to be swept.
        """

        json_str = Path(config_file).read_text()
        data = json.loads(json_str)
        title = data.pop("title")
        description = data.pop("description")
        swept_args = data.pop("swept_args", {})
        submission_arg_overrides = data.pop("submission_arg_overrides", {})

        if swept_args:
            for k, v in swept_args.items():
                if k in data:
                    raise ValueError(f"Swept argument '{k}' also specified in unswept arguments")
                if not all(isinstance(item, type(v[0])) for item in v):
                    raise ValueError(f"All values for swept argument '{k}' must be of the same type")
                data[k] = v[0]
        # we include the base_path context so that any arg_class that needs to
        # resolve absolute paths can (e.g., used by HazardArgs)
        prototype = args_class.model_validate(
            data, extra='forbid', context={"base_path": Path(config_file).parent.resolve()}
        )

        return cls(prototype, swept_args, title, description, submission_arg_overrides)

    def get_tasks(self) -> Generator[BaseModel, None, None]:
        """Generate all combinations of swept arguments as job argument objects.

        Yields:
            Job argument objects for each combination of swept arguments.
        """
        from itertools import product

        if not self.swept_args:
            yield self.prototype_args
            return

        prototype_data = self.prototype_args.model_dump()
        for values in product(*self.swept_args.values()):
            update_data = dict(zip(self.swept_args.keys(), values, strict=True))
            prototype_data_copy = copy.deepcopy(prototype_data)
            yield self.prototype_args.model_validate(prototype_data_copy | update_data)

    def validate_all_tasks(self) -> None:
        """Re-run Pydantic validation on every task that would be generated.

        Raises ValidationError if the (possibly-mutated) prototype, or any swept
        combination, fails validation. Call before any dispatch side effect so
        the job fails fast instead of partway through task submission.
        """
        if not self.swept_args:
            # get_tasks() yields the prototype directly without re-validating —
            # re-validate here in case the runner __init__ mutated prototype_args.
            type(self.prototype_args).model_validate(self.prototype_args.model_dump())
            return
        for _ in self.get_tasks():
            pass
