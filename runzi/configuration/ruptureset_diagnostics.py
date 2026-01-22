import base64
import os
import stat
from pathlib import PurePath
from typing import Any, Generator

from runzi.automation.scaling.file_utils import get_output_file_id, get_output_file_ids
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    REPORT_LEVEL,
    S3_REPORT_BUCKET,
    S3_URL,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import OpenshaTaskFactory
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.execute import ruptset_diags_report_task
from runzi.execute.ruptset_diags_report_task import RuptureSetReportArgs
from runzi.configuration.arguments import SystemArgs
from runzi.util.aws import get_ecs_job_config

JVM_HEAP_MAX = 16
JAVA_THREADS = 12
MAX_JOB_TIME_MIN = 60


def build_rupset_diag_tasks(toshi_id: str) -> Generator[dict[str, Any] | str, None, None]:

    headers = {"x-api-key": API_KEY}
    file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    # for a single rupture set, pass a valid FileID, for
    if 'GeneralTask' in str(base64.b64decode(toshi_id)):
        file_generator = get_output_file_ids(file_api, toshi_id)
    else:
        file_generator = get_output_file_id(file_api, toshi_id)  # for file by file ID

    work_path = PurePath('/WORKING') if CLUSTER_MODE is EnvMode.AWS else WORK_PATH

    task_factory = OpenshaTaskFactory(
        OPENSHA_ROOT,
        WORK_PATH,
        ruptset_diags_report_task,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for task_count, rupture_set in enumerate(file_generator, start=1):

        task_args = RuptureSetReportArgs(rupture_set_id=rupture_set['id'], build_report_level=REPORT_LEVEL)
        task_system_args = SystemArgs(java_gateway_port=task_factory.get_next_port(), task_count=task_count)

        if CLUSTER_MODE == EnvMode['AWS']:
            job_name = f"Runzi-automation-inversion_diagnostic-{task_count}"

            yield get_ecs_job_config(
                job_name,
                rupture_set['id'],
                task_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=ruptset_diags_report_task.__name__,
                time_minutes=int(MAX_JOB_TIME_MIN),
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
