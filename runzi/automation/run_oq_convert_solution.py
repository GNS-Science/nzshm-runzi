
#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that convert an opensha InversionSolution
into

soucrce can be

 -  InversionSolution
  - A GT containing Inversion Solutions

"""
import datetime as dt
from dateutil.tz import tzutc
from subprocess import check_call
from multiprocessing.dummy import Pool

from scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs
from runzi.configuration.openquake_hazard import build_hazard_tasks, SubtaskType
from scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

from scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

def build_tasks(general_tasks, args, task_type):

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for gt_id in general_tasks:
        file_generator = get_output_file_ids(toshi_api, gt_id)
        solutions = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False,
            skip_download=(CLUSTER_MODE == EnvMode['AWS']))


        # print(solutions)

        for script_file in build_hazard_tasks(GENERAL_TASK_ID, task_type, solutions, args):
            print('scheduling: ', script_file)
            scripts.append(script_file)
            assert 0

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

    print('worker count: ', WORKER_POOL_SIZE)
    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None

    # If you wish to override something in the main config, do so here ..
    WORKER_POOL_SIZE = 1
    HAZARD_MAX_TIME = 15
    USE_API = True

    # #If using API give this task a descriptive setting...
    # TASK_TITLE = "Inversion diags"
    # TASK_DESCRIPTION = """
    # """

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    """
    Openquake hazard requires ...

     - a source config - with one or more source logic trees (e.g BG, Hikurangi, Puysegur, Crustal)
     - a GMM config gsim_logic_tree_file
     - a configuration file

    """

    args = dict(
        rupture_sampling_distance_km = 0.5, # Unit of measure for the rupture sampling: km
        investigation_time_years = 1.0, # Unit of measure for the `investigation_time`: years
    )

    general_tasks = ["R2VuZXJhbFRhc2s6MTAwMDEz"]
    build_tasks(general_tasks, args, SubtaskType.CONVERT_INVERSION)