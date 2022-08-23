import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath

import datetime as dt
from dateutil.tz import tzutc
from typing import Iterable

from itertools import chain

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType

from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config, BatchEnvironmentSetting
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

import runzi.execute.openquake.oq_hazard_task
from runzi.execute.openquake.util import get_logic_tree_branches, get_granular_logic_tree_branches

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode, S3_URL, S3_REPORT_BUCKET)

HAZARD_MAX_TIME = 20 #minutes

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

def build_task(task_arguments, job_arguments, task_id, extra_env):

    if CLUSTER_MODE == EnvMode['AWS']:
        job_name = f"Runzi-automation-oq-disagg-{task_id}"
        config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

        return get_ecs_job_config(job_name,
            'N/A', config_data,
            toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
            task_module=runzi.execute.openquake.oq_hazard_task.__name__,
            time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4,
            job_definition="Fargate-runzi-openquake-JD",
            extra_env = extra_env,
            use_compression = True)
    else:
        #write a config
        task_factory.write_task_config(task_arguments, job_arguments)
        script = task_factory.get_task_script()

        script_file_path = PurePath(WORK_PATH, f"task_{task_id}.sh")
        with open(script_file_path, 'w') as f:
            f.write(script)

        #make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        return str(script_file_path)


def build_hazard_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, hazard_config: str, disagg_configs: Iterable):
    task_count = 0
    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]


    for disagg_config in disagg_configs:
        for disagg_specs in disagg_config['deagg_specs']:
            
            task_count +=1

            full_config = disagg_specs.copy()
            full_config['location'] = disagg_config['location']
            full_config['site_name'] = disagg_config.get('site_name')
            full_config['vs30'] = disagg_config['vs30']
            full_config['imt'] = disagg_config['imt']
            full_config['poe'] = disagg_config['poe']
            full_config['inv_time'] = disagg_config['inv_time']
            full_config['target_level'] = disagg_config['target_level']
            full_config['level'] = disagg_config['target_level'] # this is the level at which we calculate the disagg. could be rlz_level or target_level. Has prev been rlz

            task_arguments = dict(
                hazard_config = hazard_config, #  upstream modified config File archive object
                #upstream_general_task=source_gt_id,
                model_type = model_type.name,
                disagg_config = full_config,
                )

            # print('')
            # print('task arguments MERGED')
            # print('==========================')
            # print(task_arguments)
            # print('==========================')
            # print('')

            job_arguments = dict(
                task_id = task_count,
                general_task_id = general_task_id,
                use_api = USE_API,
            )

            yield build_task(task_arguments, job_arguments, task_count, extra_env)