import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath

import datetime as dt
from dateutil.tz import tzutc

from itertools import chain

from runzi.automation.scaling.toshi_api import SubtaskType, ModelType, ToshiApi
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

import runzi.execute.time_dependent_solution_task

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )


def build_time_dependent_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, subtask_arguments, toshi_api: ToshiApi):

    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.time_dependent_solution_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    file_generators = []
    for input_id in subtask_arguments['source_solution_ids']:
        file_generators.append(get_output_file_id(toshi_api, input_id)) #for file by file ID

    source_solutions = download_files(toshi_api, chain(*file_generators), str(WORK_PATH), overwrite=False,
        skip_download=(CLUSTER_MODE == EnvMode['AWS']))

    for (src_sol_id, src_sol_info) in source_solutions.items():
        for scale in subtask_arguments['scales']:

            task_count += 1

            task_arguments = dict(
                scale = scale,
                model_type = model_type.name
            )

            print(task_arguments)

            job_arguments = dict(
                task_id = task_count,
                source_solution_id = src_sol_id,
                source_solution_info = src_sol_info,
                working_path=str(WORK_PATH),
                general_task_id=general_task_id,
                use_api = USE_API,
                )

            if CLUSTER_MODE == EnvMode['AWS']:
                    pass
                    # job_name = f"Runzi-automation-subduction_inversions-{task_count}"
                    # config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

                    # yield get_ecs_job_config(job_name, solution_info['id'], config_data,
                    #     toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                    #     task_module=inversion_solution_builder_task.__name__,
                    #     time_minutes=int(max_inversion_time), memory=30720, vcpu=4)

            else:
                #write a config
                task_factory.write_task_config(task_arguments, job_arguments)
                script = task_factory.get_task_script()

                script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
                with open(script_file_path, 'w') as f:
                    f.write(script)

                #make file executable
                st = os.stat(script_file_path)
                os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

                yield str(script_file_path)
