#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that convert an opensha InversionSolution
into source NRML XML files

 -  InversionSolution
 - A GT containing Inversion Solutions

"""
import logging
import pwd
import os
import datetime as dt
from dateutil.tz import tzutc
from subprocess import check_call
from multiprocessing.dummy import Pool

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType
from runzi.automation.scaling.toshi_api.general_task import ModelType
from runzi.configuration.oq_opensha_nrml_convert import build_nrml_tasks
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1
USE_API = True


def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_nrml_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    log = logging.getLogger(__name__)

    GENERAL_TASK_ID = None

    # #If using API give this task a descriptive setting...

    
    TASK_DESCRIPTION = """first run locally """

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    tectonic_type = 'TEST'

    if tectonic_type == 'HIK':
        TASK_TITLE = "Hikurangi Scaled NRMLs"
        model_type = ModelType.SUBDUCTION
        input_ids = [
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTA2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTA4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTE0",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTE2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTIy",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTI0",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTMw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTM0",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTM2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTQy",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTQ0",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTUw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTEw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTEy",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTE4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTIw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTI2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTI5",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTMy",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTM4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTQw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTQ2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTQ4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTU0",
        ]
    elif tectonic_type == 'PUY':
        TASK_TITLE = "Puysegur Scaled NRMLs"
        model_type = ModelType.SUBDUCTION
        input_ids = [
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDY4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDY2"
        ]
    elif tectonic_type == 'CRU':
        TASK_TITLE = "Crustal Scaled NRMLs"
        model_type = ModelType.CRUSTAL
        input_ids = [
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDcw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDc2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDc4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDgy",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDg4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDkw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDk0",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTAw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTAy",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDcy",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDc0",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDgw",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDg0",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDg2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDky",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDk2",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMDk4",
            "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAyMTA0"
        ]
    elif tectonic_type == 'TEST':
        TASK_TITLE = "Test NRMLs"
        model_type = ModelType.SUBDUCTION
        input_ids = [
            "SW52ZXJzaW9uU29sdXRpb246MTAwNDk5",
            "SW52ZXJzaW9uU29sdXRpb246MTAwNTA3",
            "SW52ZXJzaW9uU29sdXRpb246MTAwNTEw",
            "SW52ZXJzaW9uU29sdXRpb246MTAwNTEz",
            "SW52ZXJzaW9uU29sdXRpb246MTAwNTE1"
        ]

    args = dict(
        rupture_sampling_distance_km = 0.5, # Unit of measure for the rupture sampling: km 
        investigation_time_years = 1.0, # Unit of measure for the `investigation_time`: years 
        input_ids = input_ids
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.SOLUTION_TO_NRML
    

    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(task_type)\
            .set_model_type(model_type)

        new_gt_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", new_gt_id)

    tasks = build_tasks(new_gt_id, args, task_type, model_type,toshi_api)

    toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))

    print('worker count: ', WORKER_POOL_SIZE) 

    schedule_tasks(tasks,WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

