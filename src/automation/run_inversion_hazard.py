import os
import pwd
import itertools
import stat
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool

import datetime as dt
from dateutil.tz import tzutc

from scaling.toshi_api import ToshiApi

from scaling.opensha_task_factory import OpenshaTaskFactory
from scaling.file_utils import download_files, get_output_file_ids, get_output_file_id


import scaling.inversion_hazard_report_task


# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)


def run_tasks(general_task_id, solutions):
    task_count = 0
    task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.inversion_hazard_report_task,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START,
        pbs_script=CLUSTER_MODE)

    for (sid, rupture_set_info) in solutions.items():

        task_count +=1

        #get FM name
        #fault_model = rupture_set_info['info']['fault_model']
        fault_model = 'CFM_0_9_SANSTVZ_D90'

        task_arguments = dict(
            file_id = str(rupture_set_info['id']),
            file_path = rupture_set_info['filepath'],
            fault_model = fault_model,
            )
        print(task_arguments)

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
        return

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None
    # If you wish to override something in the main config, do so here ..
    WORKER_POOL_SIZE = 1
    JVM_HEAP_MAX = 42
    JAVA_THREADS = 12
    # USE_API = True #to read the ruptset form the API

    #If using API give this task a descriptive setting...
    TASK_TITLE = "Inversion diags"
    TASK_DESCRIPTION = """
    """

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    pool = Pool(WORKER_POOL_SIZE)
    for inversion_task_id in ["R2VuZXJhbFRhc2s6NTQ5ZWttekY="]: # R2VuZXJhbFRhc2s6NjMyUzRDZGM="]: #TEST Inversion

        file_generator = get_output_file_ids(toshi_api, inversion_task_id) #
        #file_generator = get_output_file_id(toshi_api, "RmlsZTozMDkuMHB3U0dn") #for file by file ID

        solutions = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        scripts = []
        for script_file in run_tasks(GENERAL_TASK_ID, solutions):
            print('scheduling: ', script_file)
            scripts.append(script_file)

        print('task count: ', len(scripts))
        pool.map(call_script, scripts)


    print('worker count: ', WORKER_POOL_SIZE)
    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
