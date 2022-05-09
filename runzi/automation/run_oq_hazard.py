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

    era_measures = ['PGA', 'SA(0.1)', 'SA(0.2)', 'SA(0.3)', 'SA(0.4)', 'SA(0.5)', 'SA(0.7)',
        'SA(1.0)', 'SA(1.5)', 'SA(2.0)', 'SA(3.0)', 'SA(4.0)', 'SA(5.0)']
    era_levels = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
        1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]

    args = dict(
        config_archive_ids = [  # a Toshi File containing zipped configuration, ], #LOCAL'RmlsZToxOA=='],
            #'RmlsZToxOA=='
            # "RmlsZToxMDE4MDQ=", #4-sites-many TEST RmlsZToxMDAzNTc=
            # "RmlsZToxMDE4MDY=", #PROD Wgn_005-10-300.ini RmlsZToxMDE4MDM= is BAD , PROD # TEST RmlsZToxMDA1MzA="
            # "RmlsZToxMDE4MDc=", #PROD Wgn_005-10-50.ini
            # "RmlsZToxMDE4MDg=", #PROD Wgn_005-4-300.ini
            #"RmlsZToxMDE4MDk=", #PROD Wgn_005-4-50.ini
            "RmlsZToxMDAzNTc="
            ],
        # source_combos = [
        #     # {'tag':'combined','nrml_ids':{
        #     #   'crustal':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Ng==",
        #     #   'hik':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OQ==",
        #     #   'bg': 'RmlsZToxMDA0ODg='}},
        #     #{'tag':'crustal_only','nrml_ids':{
        #     #   'crustal':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Ng=="}},
        #     #{'tag':'hik_only','nrml_ids':{'hik':"SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OQ=="}},
        #     {'tag': 'bg_only', 'nrml_ids': {'bg': 'RmlsZToxMDA0ODg='}},
        #     # {'tag': 'combined', 'nrml_ids': {
        #     #   'crustal': "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Mw==", #PROD "b_and_n": "{'tag': 'N = 3.5, b=0.913', PROD
        #     #   'hik': "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDMzMQ==",     #PROD "b_and_n": "{'b': 1.009, 'N': 25.6}"
        #     #   'bg': "RmlsZToxMDE4MDI=" #BG_Kiran_fADDTOT346ave_Test4 unscaled BG TEST RmlsZToxMDA1MzU=
        #     #   #'slab': "ABBBV"
        #     #   #'puy' : "ABCB"
        #     # }}
        #     ],
        # logic_tree_permutations = [
        #     {
        #         "CR": {
        #             "CR_N7.8_b_1.111_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0NA==",
        #             "CR_N7.8_b_1.111_s2": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0NQ==",
        #             "CR_N3.5_b0.913_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Ng==",
        #             #"CR_N3.5_b0.913_s2": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Nw=="
        #             },
        #         "HK": {
        #             "HK_N25.6_b0.942_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OA==",
        #             "HK_N25.6_b1.009_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OQ==",
        #             #"HK_N25.6_b1.009_s12": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM1MA=="
        #         },
        #         "BG": {
        #             "bgA": "RmlsZToxMDE4MDI="
        #         },
        #         "PY": {
        #             "PY_N": "RmlsZToxMDE4MDA="
        #         }
        #     },
        #     #MORE of these ....
        # ],

        # logic_tree_permutations = [
        #     {
        #         "tag": "all rate combinations", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "HIK",
        #                 "members" : [
        #                     {"tag": "HTC_b0.957_N16.5_C4.1_s1", "weight": 0.5, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk0OQ=="},
        #                     {"tag": "HTC_b1.078_N22.8_C4.1_s1", "weight": 0.5, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MA=="},
        #                     # {"tag": "HTL_b0.957_N16.5_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MQ=="},
        #                     # {"tag": "HTL_b1.078_N22.8_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mg=="},
        #                     # {"tag": "HTC_b0.957_N16.5_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mw=="},
        #                     # {"tag": "HTC_b0.957_N16.5_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NA=="},
        #                     # {"tag": "HTC_b1.078_N22.8_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NQ=="},
        #                     # {"tag": "HTC_b1.078_N22.8_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Ng=="},
        #                     # {"tag": "HTL_b0.957_N16.5_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Nw=="},
        #                     # {"tag": "HTL_b0.957_N16.5_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OA=="},
        #                     # {"tag": "HTL_b1.078_N22.8_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OQ=="},
        #                     # {"tag": "HTL_b1.078_N22.8_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk2MA=="}
        #                 ]
        #             },
        #             {   "group": "PUY",
        #                 "members" : [
        #                     {"tag": "P_b0.75_N3.4_C3.9_s1", "weight":1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="}
        #                 ]
        #             },
        #             {   "group": "CRU",
        #                 "members" : [
        #                     {"tag": "CR_N8.0_b1.115_C4.3_s1", "weight": 0.5, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OA=="},
        #                     {"tag": "CR_N2.3_b0.807_C4.2_s1", "weight": 0.5, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MA=="},
        #                     # {"tag": "CR_N3.7_b0.929_C4.2_s1", "weight": 0.35, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MQ=="},
        #                     # {"tag": "CR_N8.0_b1.115_C4.3_s0.51", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMg=="},
        #                     # {"tag": "CR_N2.3_b0.807_C4.2_s0.51", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNg=="},
        #                     # {"tag": "CR_N3.7_b0.929_C4.2_s0.51", "weight": 0.075, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNw=="},
        #                     # {"tag": "CR_N2.3_b0.807_C4.2_s1.62", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxOA=="},
        #                     # {"tag": "CR_N8.0_b1.115_C4.3_s1.62", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMQ=="},
        #                     # {"tag": "CR_N3.7_b0.929_C4.2_s1.62", "weight": 0.075, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNA=="}
        #                 ]
        #             },
        #             {   "group": "BG",
        #                 "members" : [
        #                     {"tag": "floor_addtot346ave", "weight":1.0, "toshi_id": "RmlsZToxMDIyMzA="}
        #                 ]
        #             }
        #         ]
        #     }
        # ],
        logic_tree_permutations = [
            {
                "tag": "all rate combinations", "weight": 1.0,
                "permute" : [
                    {   "group": "HIK",
                        "members" : [
                            {"tag": "HTC_b0.957_N16.5_C4.1_s1", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDg2Nw==" }
                            ]
                    }
                ]
            }
        ],
        intensity_specs = [
            {"tag": "lite", "measures": ['PGA', 'SA(0.5)', 'SA(1.0)'], "levels": 'logscale(0.005, 4.00, 30)' },
            # {"tag": "fixed", "measures": era_measures, "levels": era_levels},
            # {"tag": "max10-300", "measures": era_measures, "levels": 'logscale(0.005, 10.00, 300)'}
        ],
        vs30s = [ 455, ],
        location_codes = ['NZ4', 'NZ34'],
        disagg_confs = [{'enabled': False, 'config': {}},
            # {'enabled': True, 'config': {}}
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
