import datetime as dt
import itertools
import os
import pwd
import stat
from itertools import chain
from pathlib import PurePath

import boto3
from dateutil.tz import tzutc

import runzi.execute.oq_opensha_convert_task
from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids
from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, USE_API, WORK_PATH, EnvMode
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType, ToshiApi
from runzi.util.aws import get_ecs_job_config


def build_nrml_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, subtask_arguments, toshi_api: ToshiApi):

    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.oq_opensha_convert_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    file_generators = []
    for input_id in subtask_arguments['input_ids']:

        file_generators.append(get_output_file_id(toshi_api, input_id)) #for file by file ID

    solutions = download_files(toshi_api, chain(*file_generators), str(WORK_PATH), overwrite=False,
        skip_download=(CLUSTER_MODE == EnvMode['AWS']))

    for (sid, solution_info) in solutions.items():

        task_count +=1

        # # The `tectonic_region_type` label must be consistent with what you use in the
        # # logic tree for the ground-motion characterisation
        # # Use "Subduction Interface" or "Active Shallow Crust"
        # tectonic_region_type = "Subduction Interface"
        if model_type == ModelType.CRUSTAL:
            tectonic_region_type = "Active Shallow Crust"
        elif model_type == ModelType.SUBDUCTION:
            tectonic_region_type = "Subduction Interface"

        task_arguments = dict(
            rupture_sampling_distance_km = subtask_arguments['rupture_sampling_distance_km'], # Unit of measure for the rupture sampling: km 
            investigation_time_years = subtask_arguments['investigation_time_years'], # Unit of measure for the `investigation_time`: years 
            tectonic_region_type = tectonic_region_type,
            solution_id = str(solution_info['id']),
            file_name = solution_info['info']['file_name'],
            model_type = model_type.name,
            prefix = str(solution_info['id'])
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

            yield get_ecs_job_config(job_name,
                solution_info['id'], config_data,
                toshi_api_url=API_URL, toshi_s3_url=None, toshi_report_bucket=None,
                task_module=runzi.execute.oq_opensha_convert_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4) #TODO HAZARD_MAX_TIME not defined

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