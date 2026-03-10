#! schedule_tasks.py
"""
common function to schedule tasks as needed for given environment
"""

from collections.abc import Sequence
from multiprocessing.dummy import Pool
from subprocess import check_call
from typing import Any, Optional

import boto3

from runzi.automation import local_config
from runzi.automation.local_config import WORKER_POOL_SIZE, EnvMode


def schedule_tasks(scripts: Sequence[Any], worker_pool_size: Optional[int] = None):

    if not (worker_pool_size):
        worker_pool_size = WORKER_POOL_SIZE

    def call_script(script_name):
        print("call_script with:", script_name)
        try:
            if local_config.CLUSTER_MODE is EnvMode.CLUSTER:
                check_call(['qsub', script_name])
            else:
                check_call(['bash', script_name])
        except Exception as err:
            print(f"check_call err: {err}")

    if local_config.CLUSTER_MODE is EnvMode.AWS:
        batch_client = boto3.client(
            service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
        )
        for script_or_config in scripts:
            print('AWS_CONFIG: ', script_or_config)
            res = batch_client.submit_job(**script_or_config)
            print(res)
    else:
        print('task count: ', len(scripts))
        print('worker count: ', worker_pool_size)
        pool = Pool(worker_pool_size)
        pool.map(call_script, scripts)
        pool.close()
        pool.join()
