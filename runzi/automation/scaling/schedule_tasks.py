#! schedule_tasks.py
"""
common function to schedule tasks as needed for given environment
"""

from subprocess import check_call
from multiprocessing.dummy import Pool

from runzi.automation.scaling.local_config import (WORKER_POOL_SIZE, CLUSTER_MODE, EnvMode )

def schedule_tasks(scripts):

    def call_script(script_name):
        print("call_script with:", script_name)
        try:
            if CLUSTER_MODE:
                check_call(['qsub', script_name])
            else:
                check_call(['bash', script_name])
        except Exception as err:
            print(f"check_call err: {err}")

    if CLUSTER_MODE == EnvMode['LOCAL']:
        print('task count: ', len(scripts))
        pool = Pool(WORKER_POOL_SIZE)
        pool.map(call_script, scripts)
        pool.close()
        pool.join()

    elif CLUSTER_MODE == EnvMode['AWS']:

        batch_client = boto3.client(
            service_name='batch',
            region_name='us-east-1',
            endpoint_url='https://batch.us-east-1.amazonaws.com')

        for script_or_config in scripts:
            print('AWS_CONFIG: ', script_or_config)
            res = batch_client.submit_job(**script_or_config)
            print(res)
