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

#from runzi.CONFIG.OQ.crustal_N_sensivity_ltb_min import logic_tree_permutations

#from runzi.CONFIG.OQ.crustal_C_sensitivity_config_w_ids_trimmed import logic_tree_permutations, gt_description
from runzi.CONFIG.OQ.hik_n_sensitivity_config import logic_tree_permutations, gt_description

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
    logging.getLogger('gql.transport').setLevel(logging.WARN)

    log = logging.getLogger(__name__)

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Hazard calcs "
    TASK_DESCRIPTION = gt_description

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    era_measures = ['PGA', 'SA(0.1)', 'SA(0.2)', 'SA(0.3)', 'SA(0.4)', 'SA(0.5)', 'SA(0.7)',
        'SA(1.0)', 'SA(1.5)', 'SA(2.0)', 'SA(3.0)', 'SA(4.0)', 'SA(5.0)']
    era_levels = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
                    1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]

    args = dict(
        config_archive_ids = [  # a Toshi File containing zipped configuration, ], #LOCAL'RmlsZToxOA=='],
            # "RmlsZToxMDQyOTc=", #PROD NZ34_SRWG_02 DONT USE- DUPLICATE TMZ
            # "RmlsZToxMDQ1MDk=",   #PROD RmlsZToxMDQ1MDk=
            # "RmlsZToxMDA5MDM="  #TEST NZ34 SRWG_02
            # "RmlsZToxMDEwMDk="   #TEST CONFIG 29_mesh
            # "RmlsZToxMDExNTY=", #New TEST CONFIG w Rotorua TAG = None
            #"RmlsZToxMDYxOTA=" #PROD CONFIG w Rotorua TAG = NZ35
            "RmlsZToxMDY1NzE=" #PROD + backbone
            ],
        # NEW FORM
        # makes better use of python
        logic_tree_permutations =  [logic_tree_permutations[0]],
        # logic_tree_permutations = [
        #     [{
        #         "tag": "all sources, with polygons", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "HIK",
        #                 "members" : [
        #                     {"tag": "Hikurangi TC b=1.07, C=4.0, s=.75", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4MQ==","bg_id":"RmlsZToxMDQ4NjI="}
        #                 ]
        #             },
        #             {   "group": "PUY",
        #                 "members" : [
        #                     {"tag": "Puysegur b=0.712, C=3.9, s=0.4", "weight":1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4Mg==" "bg_id": None}
        #                 ]
        #             },
        #             {   "group": "CRU",
        #                 "members" : [
        #                     {"tag": "Crustal b=xxx, s=1.0", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDk3Mw==","bg_id":"RmlsZToxMDQ4NjM="}
        #                 ]
        #             }
        #         ]
        #     }]
        # ],
        intensity_specs = [
            #{"tag": "lite", "measures": ['PGA', 'SA(0.5)', 'SA(1.0)'], "levels": 'logscale(0.005, 4.00, 30)' },
            { "tag": "fixed", "measures": era_measures, "levels": era_levels},
            #{"tag": "max10-300", "measures": era_measures, "levels": 'logscale(0.001, 5.00, 100)'}
            #{"tag": "super-max", "measures": era_measures, "levels": 'logscale(0.001, 10.0, 300)'}
        ],
        vs30s = [750],# 250, #300, 350, 400, 450, 750 ],
        location_codes = ['NZ34'], # NZ6, WLG
        disagg_confs = [{'enabled': False, 'config': {}},
            # {'enabled': True, 'config': {}}
        ],
        rupture_mesh_spacings = [5], #1,2,3,4,5,6,7,8,9],
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
    print(f'tasks to schedule: {len(tasks)}')

    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
