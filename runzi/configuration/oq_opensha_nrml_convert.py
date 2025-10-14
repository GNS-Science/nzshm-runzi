import base64
import os
import stat
from pathlib import PurePath
from typing import Generator

import runzi.execute.oq_opensha_convert_task
from runzi.automation.scaling.file_utils import get_output_file_id, get_output_file_ids
from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, S3_URL, WORK_PATH, EnvMode
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.runners.runner_inputs import OQOpenSHAConvertArgs, SystemArgs
from runzi.util.aws import get_ecs_job_config

HAZARD_MAX_TIME = 36 * 60


def build_nrml_tasks(convert_args: OQOpenSHAConvertArgs, system_args: SystemArgs) -> Generator[str | dict, None, None]:

    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.oq_opensha_convert_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    headers = {"x-api-key": API_KEY}
    file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    if 'GeneralTask' in str(base64.b64decode(convert_args.task.source_solution_id)):
        file_generator = get_output_file_ids(file_api, convert_args.task.source_solution_id)
    else:
        file_generator = get_output_file_id(file_api, convert_args.task.source_solution_id)  # for file by file ID

    for task_count, source_solution in enumerate(file_generator, start=1):

        task_convert_args = convert_args.model_copy(deep=True)
        task_convert_args.task.source_solution_id = source_solution['id']

        task_system_args = system_args.model_copy(deep=True)
        task_system_args.task_count = task_count

        if CLUSTER_MODE == EnvMode['AWS']:
            job_name = f"Runzi-automation-oq-convert-solution-{task_count}"

            yield get_ecs_job_config(
                job_name,
                source_solution['id'],
                task_convert_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=None,
                toshi_report_bucket=None,
                task_module=runzi.execute.oq_opensha_convert_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME),
                memory=30720,
                vcpu=4,
            )

        else:
            task_factory.write_task_config(task_convert_args, task_system_args)
            script, next_task = task_factory.get_task_script()

            script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
            with open(script_file_path, 'w') as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
