import itertools
import os
import stat
from pathlib import PurePath, Path
from typing import TYPE_CHECKING
from runzi.automation.scaling.file_utils import download_files, get_output_file_id

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
from runzi.execute import inversion_solution_builder_task
from runzi.util.aws import get_ecs_job_config

if TYPE_CHECKING:
    from runzi.runners.inversion_inputs_v2 import InversionArgs, InversionSystemArgs
    from runzi.automation.scaling.toshi_api import ToshiApi

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
# JAVA_THREADS = 4


def build_subduction_tasks(inversion_args: 'InversionArgs', system_args: 'InversionSystemArgs'):
    task_count = 0

    factory_class = get_factory(CLUSTER_MODE)

    work_path = PurePath('/WORKING') if CLUSTER_MODE is EnvMode.AWS else WORK_PATH
    task_factory = factory_class(
        OPENSHA_ROOT,
        work_path,
        inversion_solution_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=work_path,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for task_args in inversion_args.get_task_args():
        task_system_args = system_args.model_copy(deep=True)
                    
        task_system_args.task_count = task_count
        task_system_args.java_threads=int(task_args.task.threads_per_selectors[0]) * int(task_args.task.averaging_threads[0])
        task_system_args.java_gateway_port=task_factory.get_next_port()
        task_system_args.working_path=work_path
        task_system_args.opensha_root_folder=OPENSHA_ROOT
        task_system_args.use_api=USE_API
            

        if CLUSTER_MODE == EnvMode['AWS']:

            job_name = f"Runzi-automation-subduction_inversions-{task_count}"

            yield get_ecs_job_config(
                job_name,
                task_args.task.rupture_set_ids[0],  # TODO: we don't need this, can be done by task script
                task_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=inversion_solution_builder_task.__name__,
                time_minutes=task_args.task.max_inversion_times[0],
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