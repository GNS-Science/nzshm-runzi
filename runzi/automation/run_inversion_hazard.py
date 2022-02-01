import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool

import datetime as dt
from dateutil.tz import tzutc

from scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs

from runzi.automation.scaling.opensha_task_factory import get_factory
from scaling.file_utils import download_files, get_output_file_ids, get_output_file_id
from runzi.util.aws import get_ecs_job_config

import runzi.automation.scaling.inversion_hazard_report_task

# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, S3_REPORT_BUCKET, CLUSTER_MODE, EnvMode )

def run_tasks(general_task_id, solutions, subtask_arguments):
    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)
    task_factory = factory_class(OPENSHA_ROOT, WORK_PATH, runzi.automation.scaling.inversion_hazard_report_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START)

    # def run_subtask(forecast_timespans, bg_seismicitys, iml_periods, gmpes):
    #     print ( forecast_timespans, bg_seismicitys, iml_periods, gmpes )

    for (sid, rupture_set_info) in solutions.items():

        task_count +=1

        #get FM name
        fault_model = rupture_set_info['info']['fault_model']
        # fault_model = 'CFM_0_9_SANSTVZ_D90'

        task_arguments = dict(
            file_id = str(rupture_set_info['id']),
            file_path = rupture_set_info['filepath'],
            file_name = rupture_set_info['info']['file_name'],
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

        if CLUSTER_MODE == EnvMode['AWS']:

            job_name = f"Runzi-automation-hazard-{task_count}"
            config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

            yield get_ecs_job_config(job_name, rupture_set_info['id'], config_data,
                toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.automation.scaling.inversion_hazard_report_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4)

        else:
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
            #return

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None
    # If you wish to override something in the main config, do so here ..
    WORKER_POOL_SIZE = 2
    JVM_HEAP_MAX = 20
    JAVA_THREADS = 4
    HAZARD_MAX_TIME = 15
    #USE_API = False #True #to read the ruptset form the API
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
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    #[0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0]
    args = dict(
        #iml_periods = "0.0, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0".split(',').join(),
        iml_periods = [v.strip() for v in "0.0, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0".split(',')],
        bg_seismicitys = ["INCLUDE", "EXCLUDE"],
        gmpes = ["ASK_2014"],
        forecast_timespans = ['50'],
        grid_spacings = ['0.1'],
        regions = ["NZ_TEST_GRIDDED"],
        )

    pool = Pool(WORKER_POOL_SIZE)
    #"R2VuZXJhbFRhc2s6NTQ5ZWttekY="
    #"R2VuZXJhbFRhc2s6NTk2SmJXZUI="
    #"R2VuZXJhbFRhc2s6NzU0cGp4c1c="
    #"R2VuZXJhbFRhc2s6NzU2andXeTc=",
    # R2VuZXJhbFRhc2s6NjMyUzRDZGM="]: #TEST Inversion

    #PROD
    #R2VuZXJhbFRhc2s6NjA1Mlk2blUz

    #R2VuZXJhbFRhc2s6NTg4N01zRHZO  Modular Inversions: Randomness test 1 (40)
    #R2VuZXJhbFRhc2s6NTkyOHFpTjlE  Modular Inversions: Randomness test 2 (4)
    #R2VuZXJhbFRhc2s6NTkzM0RkaDNz  Modular Inversions: Randomness test 3 (24)
    scripts = []
    for inversion_task_id in ["R2VuZXJhbFRhc2s6MTY5MDZxajVT"]:
        file_generator = get_output_file_ids(toshi_api, inversion_task_id)
        solutions = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False, skip_download=(CLUSTER_MODE == EnvMode['AWS']))

        for script_file in run_tasks(GENERAL_TASK_ID, solutions, args):
            print('scheduling: ', script_file)
            scripts.append(script_file)

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
