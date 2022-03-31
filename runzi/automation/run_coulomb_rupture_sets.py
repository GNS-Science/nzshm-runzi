import os
import pwd
import itertools
import stat
import logging

from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool

import datetime as dt
from dateutil.tz import tzutc

# from nshm_toshi_client.general_task import GeneralTask
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs

from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling import coulomb_rupture_set_builder_task

# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)

logging.basicConfig(level=logging.INFO)

# If you wish to override something in the main config, do so here ..
# WORKER_POOL_SIZE = 3
# JVM_HEAP_MAX = 16
# JAVA_THREADS = 10

WORKER_POOL_SIZE = 1
JVM_HEAP_MAX = 32
JAVA_THREADS = 16
INITIAL_GATEWAY_PORT = 26533 #set this to ensure that concurrent scheduled tasks won't clash

#If using API give this task a descriptive setting...
TASK_TITLE = "Build Coulomb CFM 1.0 sans with regional depth scaling"

TASK_DESCRIPTION = """used to test effect of code change to Coulomb builder against older rupture sets that use CFM_1_0_DOM_SANSTVZ
"""

def build_tasks(general_task_id, args):
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(OPENSHA_ROOT, WORK_PATH, coulomb_rupture_set_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START)

    for ( model, min_sub_sects_per_parent,
            min_sub_sections, max_jump_distance,
            adaptive_min_distance, thinning_factor,
            max_sections,
            depth_scaling
            # use_inverted_rake
            )\
            in itertools.product(
                args['models'], args['min_sub_sects_per_parents'],
                args['min_sub_sections_list'], args['jump_limits'],
                args['adaptive_min_distances'], args['thinning_factors'],
                args['max_sections'],
                args['depth_scaling']
                # args['use_inverted_rakes']
                ):

        task_count +=1

        task_arguments = dict(
            max_sections=max_sections,
            fault_model=model, #instead of filename. filekey
            min_sub_sects_per_parent=min_sub_sects_per_parent,
            min_sub_sections=min_sub_sections,
            max_jump_distance=max_jump_distance,
            adaptive_min_distance=adaptive_min_distance,
            thinning_factor=thinning_factor,
            scaling_relationship='SIMPLE_CRUSTAL', #TMG_CRU_2017, 'SHAW_2009_MOD' default
            depth_scaling_tvz = depth_scaling['tvz'],
            depth_scaling_sans = depth_scaling['sans']
            # use_inverted_rake=use_inverted_rake
            )


        job_arguments = dict(
            task_id = task_count,
            java_threads=JAVA_THREADS,
            PROC_COUNT=JAVA_THREADS,
            JVM_HEAP_MAX=JVM_HEAP_MAX,
            java_gateway_port=task_factory.get_next_port(),
            working_path=str(WORK_PATH),
            root_folder=OPENSHA_ROOT,
            general_task_id=general_task_id,
            use_api = USE_API,
            short_name=f'{model}-{thinning_factor}',
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

        #testing
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

    #USE_API = False
    GENERAL_TASK_ID = None

    #limit test size, nomally 1000 for NZ CFM
    MAX_SECTIONS = 2000
    # MAX_SECTIONS = 50
            
    args = dict(
        ##Test parameters
        models = ["CFM_1_0_DOM_SANSTVZ"], #, "CFM_0_9_ALL_D90","CFM_0_9_SANSTVZ_2010"]
        depth_scaling = [{'tvz': 0.667, 'sans': 0.8}],
        jump_limits = [15,], #default is 15
        # jump_limits = [15,14,13,12,11,10,9,8,7,6,5,4,3,2,1], #default is 15
        adaptive_min_distances = [6,], #9] default is 6
        thinning_factors = [0,], #5, 0.1, 0.2, 0.3] #, 0.05, 0.1, 0.2]
        min_sub_sects_per_parents = [2], #3,4,5]
        min_sub_sections_list = [2],
        max_sections=[MAX_SECTIONS],
        # use_inverted_rakes=[True]
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=str(value)))

    if USE_API:
        #create new task in toshi_api
        headers={"x-api-key":API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type('RUPTURE_SET')\
            .set_model_type('CRUSTAL')
        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

        print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for script_file in build_tasks(GENERAL_TASK_ID, args):
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



