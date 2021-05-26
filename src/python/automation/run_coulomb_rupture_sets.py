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
import scaling.azimuthal_rupture_set_builder_task
import scaling.coulomb_rupture_set_builder_task


# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 3

#If using API give this task a descriptive setting...

TASK_TITLE = "Build Coulomb NZ CFM 0.3 vs 0.9 with current UCERF4 defaults"

TASK_DESCRIPTION = """
With recent UCERF4-like  settings, build rupture sets from NZ fault models

"""

def build_tasks(general_task_id, models, jump_limits, thinning_factors,
            max_sections = 1000):
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    task_count = 0
    task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.coulomb_rupture_set_builder_task,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START,
        pbs_script=CLUSTER_MODE)

    for (model, max_jump_distance, thinning_factor)in itertools.product(
            models, jump_limits, thinning_factors):

        task_count +=1

        task_arguments = dict(
            max_sections=max_sections,
            fault_model=model, #instead of filename. filekey
            max_jump_distance=max_jump_distance,
            thinning_factor=thinning_factor,
            scaling_relationship='TMG_CRU_2017', #'SHAW_2009_MOD' TODO this is currenlty not a settable parameter!
            )


        job_arguments = dict(
            task_id = task_count,
            java_threads=JAVA_THREADS,
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
        return


if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None

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

    ##Test parameters
    models = ["CFM_0_3_SANSTVZ", "CFM_0_9_SANSTVZ_D90"] #, "CFM_0_9_ALL_D90"]
    jump_limits = [15, ] #4.0, 4.5, 5.0, 5.1] #4.0, 4.5, 5.0, 5.1] # , 5.1, 5.2, 5.3]
    thinning_factors = [0.0, ] #5, 0.1, 0.2, 0.3] #, 0.05, 0.1, 0.2]

    #limit test size, nomally 1000 for NZ CFM
    MAX_SECTIONS = 100

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for script_file in build_tasks(GENERAL_TASK_ID,
        models, jump_limits,
        thinning_factors, MAX_SECTIONS):
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
