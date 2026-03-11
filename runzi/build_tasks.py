import os
import stat
from pathlib import PurePath
from typing import Any, Generator

from runzi.arguments import ArgSweeper, SystemArgs
from runzi.automation import local_config
from runzi.automation.local_config import (
    API_URL,
    ECR_DIGEST,
    FATJAR,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_REPORT_BUCKET,
    S3_URL,
    THS_RLZ_DB,
    WORK_PATH,
    ClusterModeEnum,
)
from runzi.automation.opensha_task_factory import get_factory
from runzi.automation.toshi_api import ModelType
from runzi.aws import get_ecs_job_config
from runzi.protocols import ModuleWithDefaultSysArgs

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash


def build_tasks(
    user_args: ArgSweeper,
    system_args: SystemArgs,
    task_module: ModuleWithDefaultSysArgs,
    model_type: ModelType,
    job_name: str,
) -> Generator[dict[str, Any] | str, None, None]:
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    factory_class = get_factory(local_config.CLUSTER_MODE, system_args.task_language)  # type: ignore

    task_factory = factory_class.create(
        root_path=OPENSHA_ROOT,
        working_path=WORK_PATH,
        python_script_module=task_module,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=system_args.jvm_heap_max,
        jvm_heap_start=JVM_HEAP_START,
    )

    for task_count, task_args in enumerate(user_args.get_tasks(), start=1):
        task_system_args = system_args.model_copy()
        task_system_args.task_count = task_count
        task_system_args.java_gateway_port = task_factory.get_next_port()

        if local_config.CLUSTER_MODE == ClusterModeEnum.AWS:
            container_task = task_factory.get_container_task()

            job_name = f"{job_name}-{task_count}"

            yield get_ecs_job_config(
                container_task=container_task,
                model_type=model_type,
                job_name=job_name,
                task_args=task_args,
                task_system_args=task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                ths_rlz_db=THS_RLZ_DB,
                ecr_digest=ECR_DIGEST,
                task_module=task_module.__name__,
                time_minutes=system_args.ecs_max_job_time_min,
                memory=system_args.ecs_memory,
                vcpu=system_args.ecs_vcpu,
                job_definition=system_args.ecs_job_definition,
                job_queue=system_args.ecs_job_queue,
                extra_env=system_args.ecs_extra_env,
            )

        else:
            # write a config
            task_factory.write_task_config(task_args, task_system_args, model_type)

            script = task_factory.get_task_script()

            script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
            with open(script_file_path, "w") as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
