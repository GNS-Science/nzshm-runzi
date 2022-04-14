#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that run OpenquakeHazard

"""
import logging
import pwd
import os
import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_hazard import build_hazard_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1

def build_tasks(new_gt_id, args, task_type, model_type):

    scripts = []
    for script_file in build_hazard_tasks(new_gt_id, task_type, model_type, args):
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

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Hazard calcs "
    TASK_DESCRIPTION = """IMT sanity test/demo 2"""

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    args = dict(
        config_archive_ids = [  # a Toshi File containing zipped configuration, ], #LOCAL'RmlsZToxOA=='],
            "RmlsZToxMDE4MDQ=", #4-sites-many TEST RmlsZToxMDAzNTc=
            "RmlsZToxMDE4MDY=", #PROD Wgn_005-10-300.ini RmlsZToxMDE4MDM= is BAD , PROD # TEST RmlsZToxMDA1MzA="
            "RmlsZToxMDE4MDc=", #PROD Wgn_005-10-50.ini
            "RmlsZToxMDE4MDg=", #PROD Wgn_005-4-300.ini
            "RmlsZToxMDE4MDk=", #PROD Wgn_005-4-50.ini
            ],
        source_combos = [
            # {'tag':'combined','nrml_ids':{
            #      'crustal':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Ng==",
            #      'hik':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OQ==",
            #      'bg': 'RmlsZToxMDA0ODg='}},
            #{'tag':'crustal_only','nrml_ids':{
            #     'crustal':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Ng=="}},
            #{'tag':'hik_only','nrml_ids':{'hik':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OQ=="}},
            # {'tag': 'bg_only', 'nrml_ids': {'bg': 'RmlsZToxMDA0ODg='}},
            {'tag': 'combined', 'nrml_ids': {
              'crustal': "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Mw==", #PROD "b_and_n": "{'tag': 'N = 3.5, b=0.913', PROD
              'hik': "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDMzMQ==",     #PROD "b_and_n": "{'b': 1.009, 'N': 25.6}"
              'bg': "RmlsZToxMDE4MDI=" #BG_Kiran_fADDTOT346ave_Test4 unscaled BG TEST RmlsZToxMDA1MzU=
            }}
        ]
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD
    model_type = ModelType.COMPOSITE

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

    tasks = build_tasks(new_gt_id, args, task_type, model_type)

    # toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))
    print('worker count: ', WORKER_POOL_SIZE)

    print( tasks )
    schedule_tasks(tasks)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
