import os
import stat
from pathlib import PurePath
from types import ModuleType
from typing import Any, Generator, cast

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JVM_HEAP_MAX,
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
from runzi.automation.scaling.toshi_api import ModelType
from runzi.execute import crustal_inversion_solution_task, subduction_inversion_solution_task
from runzi.runners.inversion_inputs import CrustalInversionArgs, InversionArgs, SubductionInversionArgs
from runzi.runners.runner_inputs import SystemArgs
from runzi.util.aws import get_ecs_job_config

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
# JAVA_THREADS = 4


def build_inversion_tasks(
    inversion_args: InversionArgs, system_args: SystemArgs
) -> Generator[dict[str, Any] | str, None, None]:

    task_module: ModuleType
    if inversion_args.general.model_type is ModelType.SUBDUCTION:
        task_module = subduction_inversion_solution_task
    elif inversion_args.general.model_type is ModelType.CRUSTAL:
        task_module = crustal_inversion_solution_task
    else:
        raise ValueError("Model type must be SUBDUCTION or CRUSTAL")

    factory_class = get_factory(CLUSTER_MODE)

    work_path = PurePath('/WORKING') if CLUSTER_MODE is EnvMode.AWS else WORK_PATH
    task_factory = factory_class(
        OPENSHA_ROOT,
        work_path,
        task_module,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=work_path,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for task_count, task_args in enumerate(inversion_args.get_tasks(), start=1):
        if inversion_args.general.model_type is not ModelType.SUBDUCTION:
            task_args = cast(SubductionInversionArgs, task_args)
        elif inversion_args.general.model_type is ModelType.CRUSTAL:
            task_args = cast(CrustalInversionArgs, task_args)

        task_system_args = system_args.model_copy(deep=True)

        task_system_args.task_count = task_count
        averaging_threads = task_args.task.averaging_threads[0] or 1
        task_system_args.java_threads = int(task_args.task.selector_threads[0]) * int(averaging_threads)
        task_system_args.java_gateway_port = task_factory.get_next_port()
        task_system_args.use_api = USE_API

        if CLUSTER_MODE == EnvMode['AWS']:

            if inversion_args.general.model_type is not ModelType.SUBDUCTION:
                job_name = f"Runzi-automation-subduction_inversions-{task_count}"
            elif inversion_args.general.model_type is ModelType.CRUSTAL:
                job_name = f"Runzi-automation-crustal_inversions-{task_count}"

            yield get_ecs_job_config(
                job_name,
                task_args.task.rupture_set_id[0],  # TODO: we don't need this, can be done by task script
                task_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=task_module.__name__,
                time_minutes=task_args.task.max_inversion_time[0],
                memory=30720,
                vcpu=4,
            )

        else:
            # write a config
            task_factory.write_task_config(task_args, task_system_args)

            script = task_factory.get_task_script()

            script_file_path = PurePath(work_path, f"task_{task_count}.sh")
            with open(script_file_path, 'w') as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
