import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath

import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api import SubtaskType

from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

import runzi.execute.oq_hazard_task

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

def build_hazard_tasks(general_task_id: str, subtask_type: SubtaskType, subtask_arguments):
    task_count = 0

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.oq_hazard_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    for source_gt_id in subtask_arguments['general_tasks']:

        file_generator = get_output_file_ids(toshi_api, source_gt_id)
        solution_nrmls = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False,
                        skip_download=(CLUSTER_MODE == EnvMode['AWS']))

        for hazard_config_id in subtask_arguments["hazard_configs"]:
            for (sid, nrml_info) in solution_nrmls.items():

                task_count +=1

                task_arguments = dict(
                    nrml_id = str(nrml_info['id']),
                    file_name = nrml_info['info']['file_name'], #One NRML , what about multiple NRMLs
                    hazard_config_id = hazard_config_id,
                    upstream_general_task=source_gt_id
                    )

                print(task_arguments)

                job_arguments = dict(
                    task_id = task_count,
                    working_path = str(WORK_PATH),
                    general_task_id = general_task_id,
                    use_api = USE_API,
                    )

                if CLUSTER_MODE == EnvMode['AWS']:
                    job_name = f"Runzi-automation-oq-convert-solution-{task_count}"
                    config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

                    #TODO: This is commented out until it supports new oq docker image
                    # yield get_ecs_job_config(job_name,
                    #     nrml_info['id'], config_data,
                    #     toshi_api_url=API_URL, toshi_s3_url=None, toshi_report_bucket=None,
                    #     task_module=runzi.execute.oq_opensha_convert_task.__name__,
                    #     time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4)

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