import os
import pwd
import itertools
import stat
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool

import datetime as dt
from dateutil.tz import tzutc

from nshm_toshi_client.general_task import GeneralTask
from nshm_toshi_client.toshi_file import ToshiFile
from scaling.toshi_api import ToshiApi

from scaling.opensha_task_factory import OpenshaTaskFactory
from scaling.file_utils import download_files, get_output_file_id, get_output_file_ids

import scaling.ruptset_diags_report_task


# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)

# If you wish to override something in the main config, do so here ..
# WORKER_POOL_SIZE = 3
WORKER_POOL_SIZE = 2
JVM_HEAP_MAX = 12
JAVA_THREADS = 6
USE_API = True #to read the ruptset form the API


#If using API give this task a descriptive setting...
TASK_TITLE = "Baseline Inversion - Coulomb"
TASK_DESCRIPTION = """
- Coulomb rupture sets
- Fixed duration comparisons
"""

def run_tasks(general_task_id, rupture_sets):
    task_count = 0
    task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.ruptset_diags_report_task,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START,
        pbs_script=CLUSTER_MODE)

    for (rid, rupture_set_info) in rupture_sets.items():

        task_count +=1

        short_name = f"Rupture set file_id: {rid}"

        #rupture_set_info['info'] has detaail of the Inversion task
        task_arguments = dict(
            rupture_set_file_id = str(rupture_set_info['id']),
            rupture_set_file_path = rupture_set_info['filepath'],
            )

        job_arguments = dict(
            task_id = task_count,
            # round = round,
            java_threads = JAVA_THREADS,
            java_gateway_port = task_factory.get_next_port(),
            working_path = str(WORK_PATH),
            root_folder = OPENSHA_ROOT,
            general_task_id = general_task_id,
            use_api = USE_API,
            )

        #write a config
        task_factory.write_task_config(task_arguments, job_arguments)

        script = task_factory.get_task_script()

        script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
        with open(script_file_path, 'w') as f:
            f.write(script)

        #make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        yield str(script_file_path)

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None

    if USE_API:
        headers={"x-api-key":API_KEY}

        #general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        #get input files from API
        upstream_task_id = "R2VuZXJhbFRhc2s6MTk0NTJNS2dN" ##
        upstream_task_id = "R2VuZXJhbFRhc2s6NzE2YWV2a3E=" ##test
        upstream_task_id = "R2VuZXJhbFRhc2s6NzIybjVvc0I=" ## test 2
        upstream_task_id = "R2VuZXJhbFRhc2s6MjIyOHp4U2hS" ## PROD
        """
        CHOOSE ONE OF:

         - file_generator = get_output_file_id(file_api, file_id)
         - file_generator = get_output_file_ids(general_api, upstream_task_id)
        """
        #for a single rupture set, pass a valid FileID
        #file_generator = get_output_file_id(toshi_api, file_id) #for file by file ID
        file_generator = get_output_file_ids(toshi_api, upstream_task_id)

        rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        # print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    # print( rupture_sets )

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for script_file in run_tasks(GENERAL_TASK_ID, rupture_sets):
        print('scheduling: ', script_file)
        scripts.append(script_file)

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    print('task count: ', len(scripts))
    print('worker count: ', WORKER_POOL_SIZE)

    pool.map(call_script, scripts)
    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
