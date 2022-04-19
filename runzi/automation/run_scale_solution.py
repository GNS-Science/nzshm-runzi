import os
import pwd
import itertools
import stat
from pathlib import PurePath
from subprocess import run
from multiprocessing.dummy import Pool
import boto3
import logging

import datetime as dt
from dateutil.tz import tzutc

from itertools import chain

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids

from runzi.execute import scale_solution_task
from runzi.util.aws import get_ecs_job_config

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, S3_REPORT_BUCKET, CLUSTER_MODE, EnvMode)

INITIAL_GATEWAY_PORT = 26533 #set this to ensure that concurrent scheduled tasks won't clash
#JAVA_THREADS = 4

if CLUSTER_MODE == EnvMode['AWS']:
    WORK_PATH='/WORKING'

def build_subset_tasks(general_task_id, source_solutions, args):
    
    task_count = 0

    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(OPENSHA_ROOT, WORK_PATH, scale_solution_task,
        task_config_path=WORK_PATH )

    for (src_sol_id, src_sol_info) in source_solutions.items():

        for scale in args['scales']:
            
            task_count += 1

            task_arguments = dict(
                scale = scale,
                config_type=args['config_type']
            )

            job_arguments = dict(
                task_id = task_count,
                source_solution_id = src_sol_id,
                source_solution_info = src_sol_info,
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

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    log = logging.getLogger(__name__)

    # If you wish to oversolution_ide something in the main config, do so here ..
    WORKER_POOL_SIZE = 2
    USE_API = True
    #If using API give this task a descriptive setting...
    TASK_TITLE = "Hikurangi LTB004. Scaled 0.67, 1.41"
    TASK_DESCRIPTION = """
    
    """

    GENERAL_TASK_ID = None

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    source_solution_ids = [
        "R2VuZXJhbFRhc2s6MTAwMjQx",
    ]

    # scales = [0.49, 1.63]
    # scales = [0.61, 1.34]
    scales = [0.67, 1.41]

    model_type = 'subduction'


    file_generators = []
    for file_id in source_solution_ids:
        """
        CHOOSE ONE OF:
         - file_generator = get_output_file_id(file_api, file_id)
         - file_generator = get_output_file_ids(general_api, upstream_task_id)
        """
        file_generators.append(get_output_file_ids(toshi_api, file_id)) #for file by file ID

    source_solutions = download_files(toshi_api, chain(*file_generators), str(WORK_PATH), overwrite=False)

    args = dict(
        scales = scales,
        config_type = model_type.lower() #TODO, do I need this?
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))
    print(args_list)
    
    
    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type('SCALE_SOLUTION')\
            .set_model_type(model_type.upper()) #TODO what goes here? Can I get it from the source solution?

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    scripts = []
    for script_file in build_subset_tasks(GENERAL_TASK_ID, source_solutions, args):
        scripts.append(script_file)

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            run(['qsub', script_name])
        else:
            run(['bash', script_name])

    
    MOCK_MODE = True
    MOCK_MODE = False

    print('task count: ', len(scripts))
    print('worker count: ', WORKER_POOL_SIZE)

    if MOCK_MODE:
        #call_script = mock.Mock(call_script)
        assert 0

    pool = Pool(WORKER_POOL_SIZE)
    pool.map(call_script, scripts)
    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


