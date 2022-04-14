import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath

import datetime as dt
from dateutil.tz import tzutc

from itertools import chain

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType

from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

import runzi.execute.oq_hazard_task

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode, S3_URL, S3_REPORT_BUCKET)

HAZARD_MAX_TIME = 36*60 #minutes

def build_hazard_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, subtask_arguments):
    task_count = 0

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.oq_hazard_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    for config_archive_id in subtask_arguments["config_archive_ids"]:
        for sources in subtask_arguments['source_combos']:

            task_count +=1
            task_arguments = dict(
                # nrml_id = nrml_info['id'], #One NRML, what about multiple NRMLs
                # file_name = nrml_info['info']['file_name'],
                config_archive_id = config_archive_id, #File archive object
                #upstream_general_task=source_gt_id,
                model_type = model_type.name,
                sources = sources
                )

            print('')
            print('task arguments MERGED')
            print('==========================')
            print(task_arguments)
            print('==========================')
            print('')

            job_arguments = dict(
                task_id = task_count,
                general_task_id = general_task_id,
                use_api = USE_API,
                )

            if CLUSTER_MODE == EnvMode['AWS']:
                job_name = f"Runzi-automation-oq-hazard-{task_count}"
                config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

                yield get_ecs_job_config(job_name,
                    'N/A', config_data,
                    toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                    task_module=runzi.execute.oq_hazard_task.__name__,
                    time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4,
                    job_definition="Fargate-runzi-openquake-JD")

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

