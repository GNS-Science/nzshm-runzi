import os
import stat
from pathlib import PurePath

from runzi.automation.scaling.file_utils import get_output_file_ids

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    BUILD_PLOTS,
    CLUSTER_MODE,
    FATJAR,
    HACK_FAULT_MODEL,
    JVM_HEAP_MAX,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    REPORT_LEVEL,
    S3_REPORT_BUCKET,
    S3_URL,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.execute import inversion_diags_report_task
from runzi.runners.runner_inputs import InversionReportArgs, InversionReportSystemArgs
from runzi.util.aws import get_ecs_job_config

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
MAX_JOB_TIME_SECS = 60 * 30  # Change this soon


def generate_tasks_or_configs(general_task_id: str):

    headers = {"x-api-key": API_KEY}
    file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    file_generator = get_output_file_ids(file_api, general_task_id)
    work_path = PurePath('/WORKING') if CLUSTER_MODE is EnvMode.AWS else WORK_PATH

    factory_class = get_factory(CLUSTER_MODE)
    task_factory = factory_class(
        OPENSHA_ROOT,
        work_path,
        inversion_diags_report_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=work_path,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for task_count, solution in enumerate(file_generator):
        fault_model = solution.get('fault_model', '')
        if HACK_FAULT_MODEL:
            fault_model = HACK_FAULT_MODEL

        task_args = InversionReportArgs(
            solution_id=solution['id'],
            build_mfd_plots=BUILD_PLOTS,
            build_report_level=REPORT_LEVEL,
            fault_model=fault_model,
            general_task_id=general_task_id,
        )
        task_system_args = InversionReportSystemArgs(java_gateway_port=task_factory.get_next_port(), task_id=task_count)

        if CLUSTER_MODE == EnvMode['AWS']:
            job_name = f"Runzi-automation-inversion_diagnostic-{task_count}"

            yield get_ecs_job_config(
                job_name,
                solution['id'],
                task_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=inversion_diags_report_task.__name__,
                time_minutes=int(MAX_JOB_TIME_SECS),
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
