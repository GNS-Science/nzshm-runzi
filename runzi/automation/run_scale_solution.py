#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that scale the rates of an opensha InversionSolution

"""
import logging
import pwd
import os
import base64
import datetime as dt
from dateutil.tz import tzutc
from subprocess import check_call
from multiprocessing.dummy import Pool

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType
from runzi.automation.scaling.toshi_api.general_task import ModelType
from runzi.configuration.scale_inversion_solution import build_scale_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.file_utils import get_output_file_ids

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 27 
# WORKER_POOL_SIZE = None
USE_API = True

def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_scale_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts



    


def run(source_solution_ids, scales,
        TASK_TITLE: str, TASK_DESCRIPTION: str, WORKER_POOL_SIZE,
        polygon_scale=None, polygon_max_mag=None):
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

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    # if a GT id has been provided, unpack to get individual solution ids
    source_solution_ids_list = []
    for source_solution_id in source_solution_ids:
        if 'GeneralTask' in str(base64.b64decode(source_solution_id)):
            source_solution_ids_list += [out['id'] for out in get_output_file_ids(toshi_api, source_solution_id)]
        else:
            source_solution_ids_list += [source_solution_id]

    model_type = get_model_type(source_solution_ids_list,toshi_api)

    subtask_type = SubtaskType.SCALE_SOLUTION

    args = dict(
        scales = scales,
        polygon_scale=polygon_scale,
        polygon_max_mag=polygon_max_mag,
        source_solution_ids = source_solution_ids_list
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))
    print(args_list)
    
    
    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(subtask_type)\
            .set_model_type(model_type) 

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    tasks = build_tasks(GENERAL_TASK_ID, args, subtask_type, model_type, toshi_api)

    toshi_api.general_task.update_subtask_count(GENERAL_TASK_ID, len(tasks))

    print('worker count: ', WORKER_POOL_SIZE)

    schedule_tasks(tasks,WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return GENERAL_TASK_ID

if __name__ == "__main__":

    # #If using API give this task a descriptive setting...
    TASK_DESCRIPTION = """scale all max jump distance inversions for polygons"""
    
    
    # TASK_TITLE = "Hikurangi Noise Averages"
    # source_solution_ids = [
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzE4",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzIy",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzI0",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzI4",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzMy",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzQw",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzQ0",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzM4",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzQz",
    #     "QWdncmVnYXRlSW52ZXJzaW9uU29sdXRpb246MTA2MzQ2"
    # ]   
    # scales = [0.75, 1.0, 1.28]

    # TASK_TITLE = "Scaling Puysegur Inversions"
    # source_solution_ids = [
    #     "SW52ZXJzaW9uU29sdXRpb246MTA1NTY1",
    # ]
    # scales = [0.4, 1.0, 1.63]

    TASK_TITLE = "Scaling Crustal (geodetic slip, TD)"
    source_solution_ids = [
        "R2VuZXJhbFRhc2s6NjUzOTY5Ng==",
    ]
    scales = [0.66, 1.0, 1.41]
    polygon_scale = 0.8
    polygon_max_mag = 8
        
    # run(source_solution_ids, scales,
    #     TASK_TITLE, TASK_DESCRIPTION , WORKER_POOL_SIZE)

    run(source_solution_ids, scales, 
        TASK_TITLE, TASK_DESCRIPTION , WORKER_POOL_SIZE,
          polygon_scale=polygon_scale, polygon_max_mag=polygon_max_mag)

