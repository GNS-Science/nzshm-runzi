from operator import mod
import pwd
import logging
import os
import datetime as dt
from pyexpat import model
from statistics import mode

from runzi.configuration.average_inversion_solutions import build_average_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType
from runzi.automation.scaling.toshi_api.general_task import ModelType
from runzi.automation.scaling.task_utils import get_model_type



from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

# If you wish to override something in the main config, do so here ..
#WORKER_POOL_SIZE = 2 
WORKER_POOL_SIZE = None
USE_API = True

def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_average_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts

def run(source_solution_groups, TASK_TITLE, TASK_DESCRIPTION , WORKER_POOL_SIZE):

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

    model_type = None
    for source_solution_ids in source_solution_groups:
        new_model_type = get_model_type(source_solution_ids,toshi_api)
        if (not model_type):
            model_type = new_model_type
        else:
            if new_model_type is model_type:
                continue
            else:
                raise Exception(f'model types are not all the same for source solution groups {source_solution_groups}')


    subtask_type = SubtaskType.AGGREGATE_SOLUTION

    args = dict(
        source_solution_groups = source_solution_groups
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

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

    TASK_DESCRIPTION = 'Hikurangi Noise Averages'
    TASK_TITLE = 'Hikurangi Noise Averages. Locked and Creeping. From GTs R2VuZXJhbFRhc2s6MTAyNTQz and R2VuZXJhbFRhc2s6MTAyODEw'


    source_solution_groups = [

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 1.231, C = 3.9
        ['SW52ZXJzaW9uU29sdXRpb246MTA1MTk4', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTg3', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTU4', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTcy', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjIw',
        'SW52ZXJzaW9uU29sdXRpb246MTA1MjM5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjI0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjE1', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjA1', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjM4'],
        
        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 1.231, C = 4.0
        ['SW52ZXJzaW9uU29sdXRpb246MTA1MTI4', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTk3', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjAz', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTgx', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTkw',
       'SW52ZXJzaW9uU29sdXRpb246MTA1MTYw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjI5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjM1', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjM0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjQ3'],

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 1.231, C = 4.1
       ['SW52ZXJzaW9uU29sdXRpb246MTA1MTU3', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTQ5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTMw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjAx', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTg2',
       'SW52ZXJzaW9uU29sdXRpb246MTA1MjE5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjIz', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjIy', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjI4', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjQz'],

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 1.067, C = 3.9
       ['SW52ZXJzaW9uU29sdXRpb246MTA1MDM5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDg2', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDk4', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTM3', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTM2',
       'SW52ZXJzaW9uU29sdXRpb246MTA1MjQw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTk1', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjE2', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjAw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjQ0'],

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 1.067, C = 4.0
        ['SW52ZXJzaW9uU29sdXRpb246MTA1MDcw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDY1', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTUw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTUy', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTYz',
         'SW52ZXJzaW9uU29sdXRpb246MTA1MTUx', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTYy', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTk0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTc0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjM2'],

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 1.067, C = 4.1
        ['SW52ZXJzaW9uU29sdXRpb246MTA0OTk2', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDY5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDc0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDY3', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDg1',
        'SW52ZXJzaW9uU29sdXRpb246MTA1MTk2', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTky', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTM4', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjMw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjMx'],

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 0.942, C = 3.9
        ['SW52ZXJzaW9uU29sdXRpb246MTA0OTkw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDA5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDA4', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDU5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDU2',
         'SW52ZXJzaW9uU29sdXRpb246MTA1MTAz', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDky', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTE0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTA2', 'SW52ZXJzaW9uU29sdXRpb246MTA1MjE4'],

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 0.942, C = 4.0
        ['SW52ZXJzaW9uU29sdXRpb246MTA1MDA2', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDAw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDAx', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDE1', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDQ2', 
        'SW52ZXJzaW9uU29sdXRpb246MTA1MDYx', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTEw', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDgz', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDg5', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDg4'],

        # R2VuZXJhbFRhc2s6MTAyNTQ, b = 0.942, C = 4.1
        ['SW52ZXJzaW9uU29sdXRpb246MTA1MDQy', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDcx', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDI0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDQ3', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDkz',
         'SW52ZXJzaW9uU29sdXRpb246MTA1MDY0', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDUz', 'SW52ZXJzaW9uU29sdXRpb246MTA1MDYz', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTM1', 'SW52ZXJzaW9uU29sdXRpb246MTA1MTAx'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 1.231, C = 3.9
        ['SW52ZXJzaW9uU29sdXRpb246MTA1ODk2', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTYx', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTQ2', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTg4', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTgx',
         'SW52ZXJzaW9uU29sdXRpb246MTA2MDE1', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDEx', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDEz', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDIy', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDIw'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 1.231, C = 4.0
        ['SW52ZXJzaW9uU29sdXRpb246MTA1ODYw', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTY5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTY1', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTc4', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTUx', 
         'SW52ZXJzaW9uU29sdXRpb246MTA1OTYz', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTk3', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDA3', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDIx', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDI0'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 1.231, C = 4.1
        ['SW52ZXJzaW9uU29sdXRpb246MTA1OTMy', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTI4', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTU2', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTY3', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTkz',
         'SW52ZXJzaW9uU29sdXRpb246MTA1OTkx', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDAx', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDAz', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDEy', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDI3'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 1.067, C = 3.9
        ['SW52ZXJzaW9uU29sdXRpb246MTA1Nzc3', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODI1', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODky', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODcz', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTA5',
         'SW52ZXJzaW9uU29sdXRpb246MTA1OTM5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTcz', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTQ0', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTg5', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDEw'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 1.067, C = 4.0
        ['SW52ZXJzaW9uU29sdXRpb246MTA1Nzk0', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODM5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTEx', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTA3', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTE2',
         'SW52ZXJzaW9uU29sdXRpb246MTA1ODk4', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTQ4', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTg3', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTI2', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTk2'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 1.067, C = 4.1
        ['SW52ZXJzaW9uU29sdXRpb246MTA1ODU1', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODA4', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTQz', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODQ3', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODc4',
         'SW52ZXJzaW9uU29sdXRpb246MTA1OTQw', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODk3', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTU5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTQ3', 'SW52ZXJzaW9uU29sdXRpb246MTA2MDE4'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 0.942, C = 3.9
        ['SW52ZXJzaW9uU29sdXRpb246MTA1NzY2', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODE1', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODM2', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODQw', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODg1',
         'SW52ZXJzaW9uU29sdXRpb246MTA1ODIy', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODIx', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODc5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTI1', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTM4'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 0.942, C = 4.0
        ['SW52ZXJzaW9uU29sdXRpb246MTA1Nzgx', 'SW52ZXJzaW9uU29sdXRpb246MTA1Nzgw', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODI3', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODI0', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODk5',
         'SW52ZXJzaW9uU29sdXRpb246MTA1ODY5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTIx', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTc5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTU1', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTM0'],

        # R2VuZXJhbFRhc2s6MTAyODEw, b = 0.942, C = 4.1
        ['SW52ZXJzaW9uU29sdXRpb246MTA1NzY4', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODE4', 'SW52ZXJzaW9uU29sdXRpb246MTA1Nzc5', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTMx', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODcx',
         'SW52ZXJzaW9uU29sdXRpb246MTA1ODcy', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODkw', 'SW52ZXJzaW9uU29sdXRpb246MTA1ODQ2', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTAy', 'SW52ZXJzaW9uU29sdXRpb246MTA1OTk0'],
    ]


    run(source_solution_groups, TASK_TITLE, TASK_DESCRIPTION , WORKER_POOL_SIZE)

