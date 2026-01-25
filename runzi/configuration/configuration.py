import os
import stat
from itertools import product
from pathlib import PurePath
from typing import Any, Generator, Optional

from typing_extensions import Sequence

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
from runzi.execute.arguments import ArgSweeper, SystemArgs
from types import ModuleType
from runzi.util.aws import get_ecs_job_config

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash


def build_tasks(rupture_set_args: ArgSweeper, system_args: SystemArgs, task_module: ModuleType) -> Generator[dict[str, Any] | str, None, None]:
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(
        OPENSHA_ROOT,
        WORK_PATH,
        task_module,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=system_args.jvm_heap_max,
        jvm_heap_start=JVM_HEAP_START,
    )

    for task_count, task_args in enumerate(rupture_set_args.get_tasks(), start=1):

        task_system_args = system_args.model_copy()
        task_system_args.task_count = task_count
        task_system_args.java_gateway_port = task_factory.get_next_port()

        if CLUSTER_MODE == EnvMode['AWS']:

            job_name = f"{task_system_args.job_name}-{task_count}"

            yield get_ecs_job_config(
                job_name,
                task_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=coulomb_rupture_set_builder_task.__name__,
                time_minutes=system_args.max_job_time_min,
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
