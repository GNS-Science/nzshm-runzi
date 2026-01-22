from itertools import product
import os
import stat
from pathlib import PurePath
from typing import Any, Generator

from pydantic import BaseModel, model_validator
from typing_extensions import Self, Sequence

from runzi.automation.scaling.local_config import (
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_REPORT_BUCKET,
    S3_URL,
    USE_API,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.execute import coulomb_rupture_set_builder_task
from runzi.runners.inversion_inputs import DEFAULT_FIELD, CoulombRuptureSetsInput
from runzi.configuration.arguments import ArgBase, SystemArgs
from runzi.util.aws import get_ecs_job_config

JVM_HEAP_MAX = 32
JAVA_THREADS = 16
INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
MAX_JOB_TIME_MIN = 60


class CoulombRuptureSetArgs(ArgBase):
    """Input for generating Coulomb rupture sets."""

    class DepthScaling(BaseModel):
        tvz: float
        sans: float

    class FaultModelFile(BaseModel):
        tag: str
        archive_id: str

    max_sections: list[int]
    max_jump_distance: list[float]
    adaptive_min_distance: list[float]
    thinning_factor: list[float]
    min_sub_sects_per_parent: list[int]
    min_sub_sections: list[int]
    scaling_relationship: list[str]
    depth_scaling: Sequence[DepthScaling | None] = DEFAULT_FIELD
    fault_model: Sequence[str | None] = DEFAULT_FIELD
    fault_model_file: Sequence[FaultModelFile | None] = DEFAULT_FIELD
    named_faults_file: Sequence[FaultModelFile | None] = DEFAULT_FIELD

    @model_validator(mode='after')
    def _check_fault_model(self) -> Self:
        """Must specify either fault_model or fault_model_file"""
        has_fault_model = self.fault_model != DEFAULT_FIELD
        has_fault_model_file = self.fault_model_file != DEFAULT_FIELD
        if not (has_fault_model != has_fault_model_file):
            raise ValueError("Must specify fault_model or fault_model_file, not both")
        return self



def build_tasks(
    rupture_set_args: CoulombRuptureSetsInput, system_args: SystemArgs
) -> Generator[dict[str, Any] | str, None, None]:
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(
        OPENSHA_ROOT,
        WORK_PATH,
        coulomb_rupture_set_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for task_count, task_args in enumerate(rupture_set_args.get_tasks(), start=1):

        task_system_args = system_args.model_copy(deep=True)

        task_system_args.task_count = task_count
        task_system_args.java_threads = JAVA_THREADS
        task_system_args.java_gateway_port = task_factory.get_next_port()
        task_system_args.use_api = USE_API

        if CLUSTER_MODE == EnvMode['AWS']:

            job_name = f"Runzi-automation-coulomb-ruputre-sets-{task_count}"

            yield get_ecs_job_config(
                job_name,
                # task_args.task.rupture_set_id[0],  # TODO: we don't need this, can be done by task script
                "",
                task_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=coulomb_rupture_set_builder_task.__name__,
                time_minutes=MAX_JOB_TIME_MIN,
                memory=30720,
                vcpu=4,
            )

        else:
            # write a config
            task_factory.write_task_config(task_args, task_system_args)

            script = task_factory.get_task_script()

            script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
            with open(script_file_path, 'w') as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
