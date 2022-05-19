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
    logging.getLogger('gql.transport').setLevel(logging.WARN)

    log = logging.getLogger(__name__)

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Hazard calcs "
    TASK_DESCRIPTION = """BG seiemsicity by tectonic region"""

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    era_measures = ['PGA', 'SA(0.1)', 'SA(0.2)', 'SA(0.3)', 'SA(0.4)', 'SA(0.5)', 'SA(0.7)',
        'SA(1.0)', 'SA(1.5)', 'SA(2.0)', 'SA(3.0)', 'SA(4.0)', 'SA(5.0)']
    era_levels = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
                    1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]

    args = dict(
        config_archive_ids = [  # a Toshi File containing zipped configuration, ], #LOCAL'RmlsZToxOA=='],
            "RmlsZToxMDQyOTc=", #PROD NZ34_SRWG_02
            # "RmlsZToxMDQ1MDk=",   #PROD RmlsZToxMDQ1MDk=
            # "RmlsZToxMDA5MDM="  #TEST NZ34 SRWG_02
            # "RmlsZToxMDEwMDk="   #TEST CONFIG 29_mesh
            ],
        """
        SRWG 02
        """
        # logic_tree_permutations = [
        #     {
        #         "tag": "all rate combinations", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "HIK",
        #                 "members" : [
        #                     {"tag": "HTC_b0.957_N16.5_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk0OQ=="},
        #                     {"tag": "HTC_b1.078_N22.8_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MA=="},
        #                     {"tag": "HTL_b0.957_N16.5_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MQ=="},
        #                     {"tag": "HTL_b1.078_N22.8_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mg=="},
        #                     {"tag": "HTC_b0.957_N16.5_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mw=="},
        #                     {"tag": "HTC_b0.957_N16.5_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NA=="},
        #                     {"tag": "HTC_b1.078_N22.8_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NQ=="},
        #                     {"tag": "HTC_b1.078_N22.8_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Ng=="},
        #                     {"tag": "HTL_b0.957_N16.5_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Nw=="},
        #                     {"tag": "HTL_b0.957_N16.5_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OA=="},
        #                     {"tag": "HTL_b1.078_N22.8_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OQ=="},
        #                     {"tag": "HTL_b1.078_N22.8_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk2MA=="}
        #                 ]
        #             },
        #             {   "group": "PUY",
        #                 "members" : [
        #                     {"tag": "P_b0.75_N3.4_C3.9_s1", "weight":1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="}
        #                 ]
        #             },
        #             {   "group": "CRU",
        #                 "members" : [
        #                     {"tag": "CR_N8.0_b1.115_C4.3_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OA=="},
        #                     {"tag": "CR_N2.3_b0.807_C4.2_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MA=="},
        #                     {"tag": "CR_N3.7_b0.929_C4.2_s1", "weight": 0.35, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MQ=="},
        #                     {"tag": "CR_N8.0_b1.115_C4.3_s0.51", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMg=="},
        #                     {"tag": "CR_N2.3_b0.807_C4.2_s0.51", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNg=="},
        #                     {"tag": "CR_N3.7_b0.929_C4.2_s0.51", "weight": 0.075, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNw=="},
        #                     {"tag": "CR_N2.3_b0.807_C4.2_s1.62", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxOA=="},
        #                     {"tag": "CR_N8.0_b1.115_C4.3_s1.62", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMQ=="},
        #                     {"tag": "CR_N3.7_b0.929_C4.2_s1.62", "weight": 0.075, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNA=="}
        #                 ]
        #             },
        #             {   "group": "BG",
        #                 "members" : [
        #                     {"tag": "floor_addtot346ave", "weight":1.0, "toshi_id": "RmlsZToxMDQyOTY="}
        #                 ]
        #             }
        #         ]
        #     }
        # ],


        """
        Single Hikurangi
        """
        # logic_tree_permutations = [
        #     {
        #         "tag": "all rate combinations", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "HIK",
        #                 "members" : [
        #                     {"tag": "HTC_b0.957_N16.5_C4.1_s1", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDg2Nw==" }
        #                     ]
        #             }
        #         ]
        #     }
        # ],
        #],

        """
        max_jummp_distance - multiple logic_tree_permutations
        """
        # logic_tree_permutations = [
        #     [
        #     {
        #         "tag": "jump_max_distance_1KM", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "CRUSTAL",
        #                 "members" : [
        #                     {"tag": "CR_1km", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU0MA==" }
        #                     ]
        #             }
        #         ]
        #     },
        #     ],[
        #     {
        #         "tag": "jump_max_distance_3KM", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "CRUSTAL",
        #                 "members" : [
        #                     {"tag": "CR_3km", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU3OA==" }
        #                 ]
        #             }
        #         ]
        #     },
        #     ],[
        #     {
        #         "tag": "jump_max_distance_5KM", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "CRUSTAL",
        #                 "members" : [
        #                     {"tag": "CR_3km", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU0MQ==" }
        #                 ]
        #             }
        #         ]
        #     },
        #     ],[
        #     {
        #         "tag": "jump_max_distance_15KM", "weight": 1.0,
        #         "permute" : [
        #             {   "group": "CRUSTAL",
        #                 "members" : [
        #                     {"tag": "CR_15km", "weight": 1.0, "toshi_id": "SSW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU0Mg==" }
        #                 ]
        #             }
        #         ]
        #     }
        #     ]
        # ],
        """
        BG seiemsicity by tectonic region
        TODO: upload BG files to ToshiAPI and subsitute ToshiID
        """
        logic_tree_permutations : [
            [
            {
                "tag": "all sources, no polygons", "weight": 1.0,
                "permute" : [
                    {   "group": "HIK",
                        "members" : [
                            {"tag": "Hikurangi", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4MQ=="}
                        ]
                    },
                    {   "group": "PUY",
                        "members" : [
                            {"tag": "Puysegur", "weight":1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4Mg=="}
                        ]
                    },
                    {   "group": "CRU",
                        "members" : [
                            {"tag": "Crustal-no-poly", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU3OQ=="}
                        ]
                    },
                    {   "group": "BG-CRU",
                        "members" : [
                            {"tag": "BG-Crustal-no-poly", "weight":1.0, "toshi_id": "RmlsZToxMDQ4NjE="}
                        ]
                    },
                    {   "group": "BG-HIK",
                        "members" : [
                            {"tag": "BG-Hikurangi", "weight":1.0,
                            "toshi_id": "RmlsZToxMDQ4NjI="}
                        ]
                    }
                ]
            }],
            [{
                "tag": "all sources, with polygons", "weight": 1.0,
                "permute" : [
                    {   "group": "HIK",
                        "members" : [
                            {"tag": "Hikurangi", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4MQ=="}
                        ]
                    },
                    {   "group": "PUY",
                        "members" : [
                            {"tag": "Puysegur", "weight":1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4Mg=="}
                        ]
                    },
                    {   "group": "CRU",
                        "members" : [
                            {"tag": "Crustal-with-poly", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4MA=="}
                        ]
                    },
                    {   "group": "BG-CRU",
                        "members" : [
                            {"tag": "BG-Crustal-with-poly", "weight":1.0,
                            "toshi_id": "RmlsZToxMDQ4NjM="}
                        ]
                    },
                    {   "group": "BG-HIK",
                        "members" : [
                            {"tag": "BG-Hikurangi", "weight":1.0,
                            "toshi_id": "RmlsZToxMDQ4NjI="}
                        ]
                    }
                ]
            }],
            [{
                "tag": "crustal only, no polygons", "weight": 1.0,
                "permute" : [
                    {   "group": "CRU",
                        "members" : [
                            {"tag": "Crustal-no-poly", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU3OQ=="}
                        ]
                    },
                    {   "group": "BG-CRU",
                        "members" : [
                            {"tag": "BG-Crustal-no-poly", "weight":1.0,
                            "toshi_id": "RmlsZToxMDQ4NjE="}
                        ]
                    }
                ]
            }],
            [{
                "tag": "crustal only, with polygons", "weight": 1.0,
                "permute" : [
                    {   "group": "CRU",
                        "members" : [
                            {"tag": "Crustal-with-poly", "weight": 1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4MA=="}
                        ]
                    },
                    {   "group": "BG-CRU",
                        "members" : [
                            {"tag": "BG-Crustal-with-poly", "weight":1.0,
                            "toshi_id": "RmlsZToxMDQ4NjM="}
                        ]
                    }
                ]
            }]

        ]
        intensity_specs = [
            # {"tag": "lite", "measures": ['PGA', 'SA(0.5)', 'SA(1.0)'], "levels": 'logscale(0.005, 4.00, 30)' },
            # {"tag": "lite", "measures": ['PGA', 'SA(0.5)', 'SA(1.0)'], "levels": 'logscale(0.005, 4.00, 30)' },
            {"tag": "fixed", "measures": era_measures, "levels": era_levels},
            #{"tag": "max10-300", "measures": era_measures, "levels": 'logscale(0.001, 5.00, 100)'}
            {"tag": "super-max", "measures": ['SA(0.5)'], "levels": 'logscale(0.001, 10.0, 300)'}
        ],
        vs30s = [250, 300, 350, 400, 450, 750 ],
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

    print( tasks )
    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
