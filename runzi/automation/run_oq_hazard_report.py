#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL to produce a hazard report from an oq-engine hazard job

"""

import logging
import datetime as dt
from operator import gt

from runzi.automation.scaling.toshi_api import ToshiApi

from runzi.configuration.oq_hazard_report import build_hazard_report_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )


# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1

def build_tasks(args, toshi_api):
    scripts = []
    for script_file in build_hazard_report_tasks(args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts


def run(WORKER_POOL_SIZE, hazard_ids=None,gt_ids=None):

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

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    args = dict(
        hazard_ids = hazard_ids,
        gt_ids = gt_ids
    )

    tasks = build_tasks(args, toshi_api)
    print(tasks)

    print('worker count: ', WORKER_POOL_SIZE)

    schedule_tasks(tasks,WORKER_POOL_SIZE)

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


if __name__ == "__main__":

    hazard_ids = [
        # "T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTAxMDQx" #TEST
        "T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTAyMDQ5" #PROD
    ]

    gt_ids = ['R2VuZXJhbFRhc2s6MTAyMDIz']

    # run(WORKER_POOL_SIZE,gt_ids=gt_ids)
    run(WORKER_POOL_SIZE,gt_ids=gt_ids)