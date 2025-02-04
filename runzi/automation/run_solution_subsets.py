import datetime as dt
import itertools
import os
import pwd
import stat
from itertools import chain
from multiprocessing.dummy import Pool
from pathlib import PurePath
from subprocess import check_call

import boto3
from dateutil.tz import tzutc

from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JAVA_THREADS,
    JVM_HEAP_MAX,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_REPORT_BUCKET,
    S3_URL,
    USE_API,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ToshiApi
from runzi.execute import inversion_sub_solution_task
from runzi.util.aws import get_ecs_job_config

INITIAL_GATEWAY_PORT = 26533 #set this to ensure that concurrent scheduled tasks won't clash
#JAVA_THREADS = 4

if CLUSTER_MODE == EnvMode['AWS']:
    WORK_PATH='/WORKING'

def build_subset_tasks(general_task_id, source_solutions, args):
    task_count = 0

    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(OPENSHA_ROOT, WORK_PATH, inversion_sub_solution_task,
        task_config_path=WORK_PATH )

    for (solution_id, solution_info) in source_solutions.items():

        for ( rate_threshold,
                radius,
                location
            )\
            in itertools.product(
                args['rate_thresholds'],
                args['radius'],
                args['locations']
                ):

            task_count +=1

            task_arguments = dict(
                config_type=args['config_type'],
                rate_threshold=rate_threshold,
                radius=radius,
                location=location,
                solution_id = solution_id,
                fault_model = solution_info.get('fault_model', f"see {solution_id}"),
            )

            job_arguments = dict(
                task_id = task_count,
                solution_id = solution_id,
                solution_info = solution_info,
                working_path=str(WORK_PATH),
                root_folder = OPENSHA_ROOT,
                general_task_id=general_task_id,
                use_api = USE_API,
                java_gateway_port=task_factory.get_next_port(),
                )

            if CLUSTER_MODE == EnvMode['AWS']:
                pass
                # job_name = f"Runzi-automation-subduction_inversions-{task_count}"
                # config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

                # yield get_ecs_job_config(job_name, solution_info['id'], config_data,
                #     toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                #     task_module=inversion_solution_builder_task.__name__,
                #     time_minutes=int(max_inversion_time), memory=30720, vcpu=4)

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

    # If you wish to oversolution_ide something in the main config, do so here ..
    WORKER_POOL_SIZE = 1
    USE_API = True
    #If using API give this task a descriptive setting...
    TASK_TITLE = "Inversion Subset test on 60m #2"
    TASK_DESCRIPTION = """
    Upgrade to new ToshiAPI

    First cut for sanity checking
     - no named fault views
     - Everthing need scrutiny!
     - target slip rates look wrong
    """

    GENERAL_TASK_ID = None

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    solution_ids = [
        "SW52ZXJzaW9uU29sdXRpb246MTY3NDIuMFVrbXJl", #60m PROD
    ]
    # "SW52ZXJzaW9uU29sdXRpb246MTY3NzUuMGthM0hM", #240m
    # "SW52ZXJzaW9uU29sdXRpb246MTY4MDMuMGdGUGpz", #480
    # "SW52ZXJzaW9uU29sdXRpb246MTY4MzQuMHN2R0hT" #960

    # #test
    # solution_ids = [
    #     "SW52ZXJzaW9uU29sdXRpb246Mjc0OC4wekZNcmk="
    # ]

    file_generators = []
    for file_id in solution_ids:
        """
        CHOOSE ONE OF:
         - file_generator = get_output_file_id(file_api, file_id)
         - file_generator = get_output_file_ids(general_api, upstream_task_id)
        """
        file_generators.append(get_output_file_id(toshi_api, file_id)) #for file by file ID

    source_solutions = download_files(toshi_api, chain(*file_generators), str(WORK_PATH), overwrite=False)

    args = dict(
        rate_thresholds = [1e-15, 1e-9, 0],
        radius = [2e5, 4e5],
        locations = ["Wellington", "Auckland", "Gisborne", "Christchurch"],
        src_solutions = solution_ids,
        config_type = 'crustal'
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    #TODO: add new type INVERSION_SUBSET
    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type('INVERSION')\
            .set_model_type('CRUSTAL')

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    scripts = []
    for script_file in build_subset_tasks(GENERAL_TASK_ID, source_solutions, args):
        scripts.append(script_file)

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    MOCK_MODE = True

    print('task count: ', len(scripts))
    print('worker count: ', WORKER_POOL_SIZE)

    # if MOCK_MODE:
    #     call_script = mock.Mock(call_script)

    pool = Pool(WORKER_POOL_SIZE)
    pool.map(call_script, scripts)
    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


