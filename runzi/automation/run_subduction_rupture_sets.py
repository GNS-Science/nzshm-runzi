"""
Configuration for building subduction rupture sets.
"""
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
from scaling.opensha_task_factory import OpenshaTaskFactory

import scaling.subduction_rupture_set_builder_task


# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1
JVM_HEAP_MAX = 12
JVM_HEAP_START = 2


def build_tasks(general_task_id, mmodels, min_aspect_ratios, max_aspect_ratios, aspect_depth_thresholds, min_fill_ratios,
            growth_position_epsilons, growth_size_epsilons, scaling_relationships, deformation_models):
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    task_count = 0
    task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.subduction_rupture_set_builder_task,
        initial_gateway_port=25733,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START,
        pbs_ppn=JAVA_THREADS,
        pbs_script=CLUSTER_MODE)

    for (model, min_aspect_ratio, max_aspect_ratio, aspect_depth_threshold,
            min_fill_ratio, growth_position_epsilon, growth_size_epsilon, scaling_relationship, deformation_model) in itertools.product(
            models, min_aspect_ratios, max_aspect_ratios, aspect_depth_thresholds, min_fill_ratios,
            growth_position_epsilons, growth_size_epsilons, scaling_relationships, deformation_models):

        task_count +=1

        task_arguments = dict(
            fault_model=model,
            min_aspect_ratio = min_aspect_ratio,
            max_aspect_ratio = max_aspect_ratio,
            aspect_depth_threshold = aspect_depth_threshold,
            min_fill_ratio = min_fill_ratio,
            growth_position_epsilon = growth_position_epsilon,
            growth_size_epsilon = growth_size_epsilon,
            scaling_relationship = scaling_relationship,
            slip_along_rupture_model = 'UNIFORM',
            deformation_model = deformation_model
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

    GENERAL_TASK_ID = None
    #USE_API = False

    #If using API give this task a descriptive setting...
    TASK_TITLE = "Build Hikurangi/Louisville ruptsets with new Fault model SBD_0_3_HKR_LR_30"

    TASK_DESCRIPTION = """

    """

    if USE_API:
        headers={"x-api-key":API_KEY}
        general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        #create new task in toshi_api
        GENERAL_TASK_ID = general_api.create_task(
            created=dt.datetime.now(tzutc()).isoformat(),
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
        )

        print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    ##Test parameters
    models = ["SBD_0_2A_HKR_LR_30", ] #"SBD_0_1_HKR_KRM_10"]

    min_aspect_ratios = [2.0,]
    max_aspect_ratios = [5.0,]
    aspect_depth_thresholds = [5,]
    min_fill_ratios = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
    growth_position_epsilons = [0.0] #0.02, 0.01]
    growth_size_epsilons =  [0.0] #0.02, 0.01]
    scaling_relationships = ["TMG_SUB_2017"]
    deformation_models = [None,]

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for script_file in build_tasks(GENERAL_TASK_ID,
        models, min_aspect_ratios, max_aspect_ratios, aspect_depth_thresholds, min_fill_ratios,
        growth_position_epsilons, growth_size_epsilons, scaling_relationships, deformation_models):
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
