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

import scaling.inversion_solution_builder_task

# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)


def build_crustal_tasks(general_task_id, rupture_sets, rounds, completion_energies, max_inversion_times,
        mfd_equality_weights, mfd_inequality_weights, slip_rate_weighting_types,
        slip_rate_weights, slip_uncertainty_scaling_factors, slip_rate_normalized_weights, slip_rate_unnormalized_weights,
        seismogenic_min_mags):
    task_count = 0
    task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.inversion_solution_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START,
        pbs_ppn=JAVA_THREADS,
        pbs_script=CLUSTER_MODE)

    for (rid, rupture_set_info) in rupture_sets.items():
        for (round, completion_energy, max_inversion_time,
                mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
                slip_rate_weight, slip_uncertainty_scaling_factor,
                slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                seismogenic_min_mag)\
            in itertools.product(
                rounds, completion_energies, max_inversion_times,
                mfd_equality_weights, mfd_inequality_weights, slip_rate_weighting_types,
                slip_rate_weights, slip_uncertainty_scaling_factors,
                slip_rate_normalized_weights, slip_rate_unnormalized_weights,
                seismogenic_min_mags):

            task_count +=1

            task_arguments = dict(
                round = round,
                config_type = 'crustal',
                rupture_set_file_id=rupture_set_info['id'],
                rupture_set=rupture_set_info['filepath'],
                completion_energy=completion_energy,
                max_inversion_time=max_inversion_time,
                mfd_equality_weight=mfd_equality_weight,
                mfd_inequality_weight=mfd_inequality_weight,
                slip_rate_weighting_type=slip_rate_weighting_type,
                slip_rate_weight=slip_rate_weight,
                slip_uncertainty_scaling_factor=slip_uncertainty_scaling_factor,
                slip_rate_normalized_weight=slip_rate_normalized_weight,
                slip_rate_unnormalized_weight=slip_rate_unnormalized_weight,
                seismogenic_min_mag=seismogenic_min_mag
                )

            job_arguments = dict(
                task_id = task_count,
                round = round,
                java_threads=JAVA_THREADS,
                jvm_heap_max = JVM_HEAP_MAX,
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
            return

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    # If you wish to override something in the main config, do so here ..
    # WORKER_POOL_SIZE = 3
    WORKER_POOL_SIZE = 1
    JVM_HEAP_MAX = 30
    JAVA_THREADS = 4
    USE_API = False

    INITIAL_GATEWAY_PORT = 26933 #set this to ensure that concurrent scheduled tasks won't clash

    INITIAL_GATEWAY_PORT = 26933 #set this to ensure that concurrent scheduled tasks won't clash


    #If using API give this task a descriptive setting...
    TASK_TITLE = "Inversions: Coulomb D90 with new minimum magnitudes "
    TASK_DESCRIPTION = """

    IN U3 then min_mag on seismogenic ruptures was 6.0, but here we test higher values (6.8. 7.0).

     - completion_energies = [0.0,]
     - max_inversion_times = [8*60,]
     - mfd_equality_weights = [1e2, 1e3, 1e4]
     - mfd_inequality_weights = [1e2, 1e3, 1e4]
     - slip_rate_weighting_types = ['BOTH',]
     - slip_rate_normalized_weights = [1e2, 1e3, 1e4]
     - slip_rate_unnormalized_weights = [1e2, 1e3, 1e4]
     - seismogenic_min_mags  = [6.8, 7.0]
    """
    GENERAL_TASK_ID = None

    headers={"x-api-key":API_KEY}
    general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    # file_api = ToshiFile(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    #get input files from API
    #upstream_task_id = "R2VuZXJhbFRhc2s6Mjk2MmlTNEs=" #Azimuthal
    #upstream_task_id = "R2VuZXJhbFRhc2s6OTMyNDRibg==" #COulomb NZ CFM 0.3 & 0.9 with current UCERF4 defaults
    #upstream_task_id = "R2VuZXJhbFRhc2s6MjUzQjdjOU4=" #TEST API


    file_id = "RmlsZTozMDMuMEJCOVVY" #PROD D90 Coulomb
    file_id = "RmlsZTo4NTkuMDM2Z2Rw" #PROD 2010_Coulomb
    #file_id = "RmlsZTo2LjB2NHVOVA==" # DEV LOCAL
    #file_id = "RmlsZToxMzY1LjBzZzRDeA==" #TEST (Subduction)

    """
    CHOOSE ONE OF:

     - file_generator = get_output_file_id(file_api, file_id)
     - file_generator = get_output_file_ids(general_api, upstream_task_id)
    """
    #for a single rupture set, pass a valid FileID
    file_generator = get_output_file_id(file_api, file_id) #for file by file ID

    rupture_sets = download_files(file_api, file_generator, str(WORK_PATH), overwrite=False)

    if USE_API:
        #create new task in toshi_api
        GENERAL_TASK_ID = general_api.create_task(
            created=dt.datetime.now(tzutc()).isoformat(),
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
        )

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    rounds = range(1)
    completion_energies = [0.0,] # 0.005]
    max_inversion_times = [10, ] #8*60,] #3*60,]  #units are minutes
    #max_inversion_times.reverse()

    seismogenic_min_mags  = [6.8, 7.0]

    mfd_equality_weights = [1e2, 1e3, 1e4]
    mfd_inequality_weights = [1e2, 1e3, 1e4]

    slip_rate_weighting_types = ['BOTH'] #NORMALIZED_BY_SLIP_RATE', UNCERTAINTY_ADJUSTED',]

    #these are used for UNCERTAINTY_ADJUSTED
    slip_rate_weights = [None, ] # 1e5, 1e4, 1e3, 1e2]
    slip_uncertainty_scaling_factors = [None, ] #2,]

    #these are used for BOTH, NORMALIZED and UNNORMALIZED
    slip_rate_normalized_weights = [1e2, 1e3, 1e4]
    slip_rate_unnormalized_weights = [1e2, 1e3, 1e4]

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for script_file in build_crustal_tasks(GENERAL_TASK_ID,
        rupture_sets, rounds, completion_energies, max_inversion_times,
        mfd_equality_weights, mfd_inequality_weights, slip_rate_weighting_types,
        slip_rate_weights, slip_uncertainty_scaling_factors,
        slip_rate_normalized_weights, slip_rate_unnormalized_weights,
        seismogenic_min_mags
        ):
        # print('scheduling: ', script_file)
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
