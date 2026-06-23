import copy
import json
from collections.abc import Generator, Sequence
from enum import Enum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from runzi.aws import BatchEnvironmentSetting


class TaskLanguage(Enum):
    PYTHON = 'python'
    JAVA = 'java'


class ComputeEnvironment(Enum):
    """Which AWS Batch compute target a job runs on.

    Fargate is the default for every task; EC2 is an explicit per-job opt-in (set via a config
    file's sys_arg_overrides) for jobs that need a size or instance feature Fargate can't
    provide. See docs/usage/aws_batch.md.
    """

    FARGATE = 'fargate'
    EC2 = 'ec2'


# Canonical AWS Batch compute target. All tasks share a single Fargate compute environment,
# job definition, and queue (see docs/architecture/adr/0003-aws-batch-compute-consolidation.md).
DEFAULT_JOB_DEFINITION = "Fargate-runzi-opensha-JD"
DEFAULT_JOB_QUEUE = "BasicFargate_Q"


class SystemArgs(BaseModel):
    task_language: TaskLanguage
    general_task_id: str | None = None
    task_count: int = 0
    use_api: bool

    java_threads: int | None = None  # only used for pbs mode, which is not supported anymore
    jvm_heap_max: int | None = None
    java_gateway_port: int | None = None

    ecs_max_job_time_min: int
    ecs_memory: int
    ecs_vcpu: int
    ecs_job_definition: str = DEFAULT_JOB_DEFINITION
    ecs_job_queue: str = DEFAULT_JOB_QUEUE
    ecs_compute_environment: ComputeEnvironment = ComputeEnvironment.FARGATE
    ecs_extra_env: list[BatchEnvironmentSetting] | None = None


class ArgSweeper:
    """Class to hold argument prototype and swept arguments."""

    def __init__(
        self,
        prototype_args: BaseModel,
        swept_args: dict[str, Sequence[Any]],
        title: str,
        description: str,
        sys_arg_overrides: dict[str, Any] | None = None,
    ):
        """Initialize a SweptArgs instance.

        Args:
            prototype: The prototype job argument object.
            swept_args: A dictionary of argument names to lists of values to be swept.
            title: The title for the job.
            description: The description for the job.
            sys_arg_overrides: System arguments to override from the default of the JobRunner.
        """

        self.prototype_args = prototype_args
        self.swept_args = swept_args
        self.title = title
        self.description = description
        self.sys_arg_overrides = sys_arg_overrides or {}

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
        sys_arg_overrides = data.pop("sys_arg_overrides", {})

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

        return cls(prototype, swept_args, title, description, sys_arg_overrides)

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
