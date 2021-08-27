import os
import pwd
import itertools
import stat
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool

import datetime as dt
from dateutil.tz import tzutc

from scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs

from scaling.opensha_task_factory import OpenshaTaskFactory
from scaling.file_utils import download_files, get_output_file_ids, get_output_file_id


import scaling.inversion_hazard_report_task

# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)


def run_tasks(general_task_id, solutions, subtask_arguments):
    task_count = 0
    task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.inversion_hazard_report_task,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START,
        pbs_script=CLUSTER_MODE)

    # def run_subtask(forecast_timespans, bg_seismicitys, iml_periods, gmpes):
    #     print ( forecast_timespans, bg_seismicitys, iml_periods, gmpes )

    for (sid, rupture_set_info) in solutions.items():

        task_count +=1

        #get FM name
        #fault_model = rupture_set_info['info']['fault_model']
        fault_model = 'CFM_0_9_SANSTVZ_D90'

        task_arguments = dict(
            file_id = str(rupture_set_info['id']),
            file_path = rupture_set_info['filepath'],
            fault_model = fault_model,
            subtask_arguments = subtask_arguments,
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
    #USE_API = False #True #to read the ruptset form the API

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

    #[0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0]
    args = dict(
        #iml_periods = "0.0, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0".split(',').join(),
        iml_periods = [v.strip() for v in "0.0, 0.25, 5.0, 10.0".split(',')],
        bg_seismicitys = ["INCLUDE"],
        gmpes = ["ASK_2014"],
        forecast_timespans = ['50',],
        grid_spacings = ['0.1'],
        regions = ["NZ_TEST_GRIDDED"],
        )

    pool = Pool(WORKER_POOL_SIZE)
    #"R2VuZXJhbFRhc2s6NTQ5ZWttekY="
    #"R2VuZXJhbFRhc2s6NTk2SmJXZUI="
    #"R2VuZXJhbFRhc2s6NzU0cGp4c1c="
    #"R2VuZXJhbFRhc2s6NzU2andXeTc=",
    for inversion_task_id in ["R2VuZXJhbFRhc2s6NzY1VDdQU3o="]: # R2VuZXJhbFRhc2s6NjMyUzRDZGM="]: #TEST Inversion

        file_generator = get_output_file_ids(toshi_api, inversion_task_id) #
        #file_generator = get_output_file_id(toshi_api, "RmlsZTozMDkuMHB3U0dn") #for file by file ID

        solutions = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        scripts = []
        for script_file in run_tasks(GENERAL_TASK_ID, solutions, args):
            print('scheduling: ', script_file)
            scripts.append(script_file)

        print('task count: ', len(scripts))
        pool.map(call_script, scripts)


    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))


    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title="Hazard on Modular with a legacy inversion solution",
            description="run hazard analyis on the given upstream GT, producing "
            )\
            .set_argument_list(args_list)\
            .set_subtask_type('HAZARD')\
            .set_model_type('CRUSTAL')

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    print('worker count: ', WORKER_POOL_SIZE)
    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
