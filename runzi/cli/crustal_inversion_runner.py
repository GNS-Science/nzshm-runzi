import os
import pwd
import datetime as dt
import boto3
from subprocess import check_call
from multiprocessing.dummy import Pool

from runzi.configuration.crustal_inversions import build_crustal_tasks
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs
from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids
from runzi.util.aws import get_secret

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE, EnvMode)

def run_crustal_inversion(config):
    t0 = dt.datetime.utcnow()

    WORKER_POOL_SIZE = config._worker_pool_size
    JVM_HEAP_MAX = config._jvm_heap_max
    JAVA_THREADS = config._java_threads
    USE_API = config._use_api
    TASK_TITLE = config._task_title
    TASK_DESCRIPTION = config._task_description
    GENERAL_TASK_ID = config._general_task_id
    MOCK_MODE = config._mock_mode
    file_id = config._file_id
    MODEL_TYPE = config._model_type
    SUBTASK_TYPE = config._subtask_type

    global WORK_PATH, API_KEY
    if CLUSTER_MODE == EnvMode['AWS']:
        WORK_PATH='/WORKING'

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    
    args = config.get_run_args()
    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    # for a file id that is a single rupture set
    #file_generator = get_output_file_id(toshi_api, file_id)
    #rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

    # for file_id that is a GT
    #file_generator = get_output_file_ids(toshi_api, file_id)
    #rupture_sets = download_files(toshi_api, file_generators, str(WORK_PATH), overwrite=False)

    # for a list of file ids in the task_args    
    #file_ids = ["RmlsZToxNTg3LjBuVm9GdA==","RmlsZToxMDEyOQ=="] little test list
    #file_ids = [rupture_set['id'] for rupture_set in args['rupture_sets']]
    rupture_sets = {}
    for rs in args['rupture_sets']:
        file_id = rs['id']
        short_name = rs['short_name']
        file_generator = get_output_file_id(toshi_api, file_id) #for file by file ID
        rupture_set = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)
        rupture_set['short_name'] = short_name
        rupture_sets.update(rupture_set)
        
        
    
    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(SUBTASK_TYPE)\
            .set_model_type(MODEL_TYPE)

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    if CLUSTER_MODE == EnvMode['AWS']:
        batch_client = boto3.client(
            service_name='batch',
            region_name='us-east-1',
            endpoint_url='https://batch.us-east-1.amazonaws.com')

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    scripts = []
    for script_file_or_config in build_crustal_tasks(GENERAL_TASK_ID, rupture_sets, args, config):
        scripts.append(script_file_or_config)

    toshi_api.general_task.update_subtask_count(GENERAL_TASK_ID, len(scripts))
    print(f"GENERAL_TASK_ID:{GENERAL_TASK_ID} with {len(scripts)} subtasks")

    if CLUSTER_MODE == EnvMode['LOCAL']:
        def call_script(script_or_config):
            print("call_script with:", script_or_config)
            check_call(['bash', script_or_config])

        print('task count: ', len(scripts))
        print('worker count: ', WORKER_POOL_SIZE)
        pool = Pool(WORKER_POOL_SIZE)
        pool.map(call_script, scripts)
        pool.close()
        pool.join()

    elif CLUSTER_MODE == EnvMode['AWS']:
        for script_or_config in scripts:
            #print('AWS_TIME!: ', script_or_config)
            res = batch_client.submit_job(**script_or_config)
            print(res)

    elif CLUSTER_MODE == EnvMode['CLUSTER']:
        for script_or_config in scripts:
            check_call(['qsub', script_or_config])

    print(f"GENERAL_TASK_ID:{GENERAL_TASK_ID} with {len(scripts)} subtasks")
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())