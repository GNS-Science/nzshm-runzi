#!python3
"""
This script produces disagg tasks in either AWS, PBS or LOCAL that run OpenquakeHazard in disagg mode.

"""
import logging
import json
import pwd
import os
import datetime as dt

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_disagg import build_hazard_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1
# USE_API = False


if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    # logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    # logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    # logging.getLogger('urllib3').setLevel(loglevel)
    # logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('gql.transport').setLevel(logging.WARN)
    log = logging.getLogger(__name__)

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Disagg calcs"
    TASK_DESCRIPTION = "Full logic tree for SLT workshop"
    #TASK_DESCRIPTION = "TEST build"

    # CONFIG_FILE = "/GNSDATA/APP/nzshm-runzi/runzi/CONFIG/DISAGG/disagg_example_TEST.json"
    # CONFIG_FILE = "/app/nzshm-runzi/runzi/CONFIG/DISAGG/disagg_example_1.json"
    # CONFIG_FILE = "/home/chrisdc/NSHM/Deaggs/deagg_configs_10.json"
    # CONFIG_FILE = "/home/chrisdc/NSHM/Disaggs/disagg_configs/deagg_configs_NZ34_02_250_WHO.json"
    # CONFIG_FILE = "/home/chrisdc/NSHM/Disaggs/disagg_configs/deagg_configs_NZ34_02_250_KBZ.json"
    CONFIG_FILE = "/home/chrisdc/NSHM/Disaggs/disagg_configs/deagg_configs_NZ34_02_250_weight_WLG_weight.json"
    # CONFIG_FILE = "/home/chrisdc/NSHM/Disaggs/disagg_configs/deagg_configs_NZ34_02_250_product_WLG.json"
    # CONFIG_FILE = "/home/chrisdc/NSHM/Disaggs/disagg_configs/deagg_configs_NZ34_02_250_product_WHO.json"
    # CONFIG_FILE = "/home/chrisdc/NSHM/Disaggs/disagg_configs/deagg_configs_NZ34_02_250_product_ZQN.json"
    

    with open(CONFIG_FILE, 'r') as df:
        disagg_configs = json.loads(df.read())

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    # TODO obtain the config (job.ini from the first nearest_rlz)
    # example from a Hazard Task ID
    # query hazard_sol {
    #   node(id:"T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTg4") {
    #     __typename
    #     ... on OpenquakeHazardSolution {
    #         modified_config {
    #           id
    #           file_name
    #           file_size
    #           file_url
    #         }
    #     }
    #   }
    # }
    # {
    #   "data": {
    #     "node": {
    #       "__typename": "OpenquakeHazardSolution",
    #       "modified_config": {
    #         "id": "RmlsZToxMTI2MTI=",
    #         "file_name": "modified_config.zip",
    #         "file_size": 4083,
    #         "file_url": "https://nzshm22-toshi-api-prod.s3.amazonaws.com/FileData/112612/modified_config.zip?AWSAccessKeyId=ASIAWW53A7TBIBPMVAHJ&Signature=BpFB0dh%2BCeWraE07yNz1rTVr40Y%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEEsaDmFwLXNvdXRoZWFzdC0yIkYwRAIgMfhCsTu4OsCeT8ka7JF38O%2FcjGCz1rDkCON%2B9ivlJNMCIHQ8OphyTms0rxj1QeP7fJ7D3yuoXugjMAp3yWJ9AeCVKqgCCIT%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQAhoMNDYxNTY0MzQ1NTM4Igz%2BvhH%2FCq15CRl4s1wq%2FAE9ls8Ugl5gdYfQw11ZGBIfpvQX7h4hKtkRQCmn1R%2F9YFdFwZJqdQAkgnMHjESOE2brrkfjhW%2BxuL4nIVeideT2PAKBOCzeQUwPMvlrJaa2FjQNqIMgNHcFPaxQIwZ3G9vwrNG5EiUs6XFRe2MFH%2Fu%2F8dOvYxnxkVuGtf0WPaWijQgT9MWDY%2BDSmHYaAgcYiSq2xVvrcgKDyK2UnbV3iBLW6ugYYYFbFxQswSTUXJI%2B22pk%2B5nPIONOOjmpTViTUwl4ZTOnlXnBUwxk1d8EsV7lRT4FuswN21jdkFLhcA%2F%2F9Ws6%2Bwiynn5Q3hYuk%2FTA1ttDAHRppguztmRjwSMwvYW%2BlgY6mwH%2B%2FNAouzzFWdMzJogeJaYxjFAVCEVqTjigiym9AfSxwQjtNdsxIbj0wpFpu%2FycZNZK8rO1NM3S9oDfAb85N%2FPe%2B77fiT3V1gnVx71QVyT57t67rDEGZaLfPVxfoK4t8SM2OjowNSVTzGg6geSwGzGG6unqad45dpU5dMjk06wBM3Z5k88RrQi15BS9LeYS9u1WHO1uQ4ocme%2Fe6A%3D%3D&Expires=1657772734"
    #       }
    #     }
    #   }
    # }

    # hazard_config = "RmlsZToxMDEyODA="  # toshi_id contain job config used by the original hazard jobs TEST for OQH : T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTAxMzE5
    # hazard_config = "RmlsZToxMTI2MTI="  # toshi_id contain job config used by the original hazard jobs PROD for OQH : T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTc3
    # hazard_config = "RmlsZToxMTQ3ODQ==" # PROD for T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA4MTU3
    hazard_config = "RmlsZToxMjEwMzQ=" # GSIM LT final v0b

    args = dict(
        hazard_config = hazard_config,
        disagg_configs =  disagg_configs,
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD #TODO: create a new task type
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

    #tasks = build_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs)

    tasks = list(build_hazard_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs))
    if USE_API:
        toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))


    print(tasks)
    print('worker count: ', WORKER_POOL_SIZE)
    print(f'tasks to schedule: {len(tasks)}')

    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
