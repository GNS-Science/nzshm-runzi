import os
import pwd
import itertools
import stat
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool

import datetime as dt
from dateutil.tz import tzutc

# from nshm_toshi_client.general_task import GeneralTask
# from nshm_toshi_client.toshi_file import ToshiFile
from scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs

from scaling.opensha_task_factory import OpenshaTaskFactory
from scaling.file_utils import download_files, get_output_file_id, get_output_file_ids

import scaling.inversion_solution_builder_task

# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)


def build_subduction_tasks(general_task_id, rupture_sets, args):
    task_count = 0
    task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.inversion_solution_builder_task,
        initial_gateway_port=27933,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START,
        pbs_ppn=JAVA_THREADS,
        pbs_script=CLUSTER_MODE)

    for (rid, rupture_set_info) in rupture_sets.items():

        for (_round, completion_energy, max_inversion_time,
                mfd_equality_weight, mfd_inequality_weight,
                slip_rate_weighting_type, slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                mfd_mag_gt_5, mfd_b_value, mfd_transition_mag,
                selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
                non_negativity_function, perturbation_function,
                )\
            in itertools.product(
                args['rounds'], args['completion_energies'], args['max_inversion_times'],
                args['mfd_equality_weights'], args['mfd_inequality_weights'],
                args['slip_rate_weighting_types'], args['slip_rate_normalized_weights'], args['slip_rate_unnormalized_weights'],
                args['mfd_mag_gt_5s'], args['mfd_b_values'], args['mfd_transition_mags'],
                args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
                args['non_negativity_function'], args['perturbation_function'],
                ):

            task_count +=1

            task_arguments = dict(
                round = _round,
                config_type = 'subduction',
                rupture_set_file_id=rupture_set_info['id'],
                rupture_set=rupture_set_info['filepath'],
                completion_energy=completion_energy,
                max_inversion_time=max_inversion_time,
                mfd_equality_weight=mfd_equality_weight,
                mfd_inequality_weight=mfd_inequality_weight,
                slip_rate_weighting_type=slip_rate_weighting_type,
                slip_rate_normalized_weight=slip_rate_normalized_weight,
                slip_rate_unnormalized_weight=slip_rate_unnormalized_weight,
                mfd_mag_gt_5=mfd_mag_gt_5,
                mfd_b_value=mfd_b_value,
                mfd_transition_mag=mfd_transition_mag,

                #New config arguments for Simulated Annealing ...
                selection_interval_secs=selection_interval_secs,
                threads_per_selector=threads_per_selector,
                averaging_threads=averaging_threads,
                averaging_interval_secs=averaging_interval_secs,
                non_negativity_function=non_negativity_function,
                perturbation_function=perturbation_function,
                )

            job_arguments = dict(
                task_id = task_count,
                # round = round,
                java_threads = int(threads_per_selector) * int(averaging_threads),
                jvm_heap_max = JVM_HEAP_MAX,
                java_gateway_port=task_factory.get_next_port(),
                working_path=str(WORK_PATH),
                root_folder=OPENSHA_ROOT,
                general_task_id=general_task_id,
                use_api = USE_API
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

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    # If you wish to override something in the main config, do so here ..
    # WORKER_POOL_SIZE = 3
    WORKER_POOL_SIZE = 1
    JVM_HEAP_MAX = 12
    JAVA_THREADS = 4
    #USE_API = False

    #If using API give this task a descriptive setting...
    TASK_TITLE = "Inversions on 30km Subduction with new Fault model SBD_0_2_HKR_LR_30"
    TASK_DESCRIPTION = """A reproduction of PROD R2VuZXJhbFRhc2s6MjY0MXE0NWY0 using modular

     - setting averaging threads = 1, and selector threads  = 4 should be similar to pre-modular setup.
     - with averaging threads = 4 we see 4 times as much CPU required.
     - NB the selection interval at 1 sec is much more frequent than the pre-modular which used 30 secs.
       This is not expected to have much effect.

    """

    GENERAL_TASK_ID = None

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    # general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    # file_api = ToshiFile(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    # file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    #file_id = "RmlsZToxNDkzLjBmbkh4eA=="
    file_id = "RmlsZToxNTMwLjBxVU5iaQ==" #TEST
    file_id = "RmlsZTo0NDYxLjBEVTRicA=="
    file_id = "RmlsZToxNTU5LjByWmtXYw==" #test new subdction
    ##file_id = "RmlsZTo1MzcwLjA5andhYw=="

    args = dict(
        rounds = [str(x) for x in range(1)],
        completion_energies = ["0.0"], # 0.005]
        max_inversion_times = ["1"], #8*60,] #3*60,]  #units are minutes
        #max_inversion_times.reverse()
        mfd_mag_gt_5s = ["29"],
        mfd_b_values = ["1.05"],
        mfd_transition_mags = ["9.15"],
        mfd_equality_weights = ["1e3", "1e4"],
        mfd_inequality_weights = ["1e3", "1e4"],
        slip_rate_weighting_types = ["BOTH"], # UNCERTAINTY_ADJUSTED,BOTH, NORMALIZED and UNNORMALIZED]
        #these are used for BOTH, NORMALIZED and UNNORMALIZED
        slip_rate_normalized_weights = ["1e3", "1e4"],
        slip_rate_unnormalized_weights = ["1e3", "1e4"],

        #New modular inversion configurations
        selection_interval_secs = ['1'],
        threads_per_selector = ['4'],
        averaging_threads = ['1', '4'],
        averaging_interval_secs = ['30'],
        non_negativity_function = ['LIMIT_ZERO_RATES'], # TRY_ZERO_RATES_OFTEN,  LIMIT_ZERO_RATES, PREVENT_ZERO_RATES
        perturbation_function = ['UNIFORM_NO_TEMP_DEPENDENCE'], # UNIFORM_NO_TEMP_DEPENDENCE, EXPONENTIAL_SCALE;
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    """
    CHOOSE ONE OF:

     - file_generator = get_output_file_id(file_api, file_id)
     - file_generator = get_output_file_ids(general_api, upstream_task_id)
    """
    #for a single rupture set, pass a valid FileID
    file_generator = get_output_file_id(toshi_api, file_id) #for file by file ID

    rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type('INVERSION')\
            .set_model_type('SUBDUCTION')

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)


    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    scripts = []
    for script_file in build_subduction_tasks(GENERAL_TASK_ID, rupture_sets, args):
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

    pool = Pool(WORKER_POOL_SIZE)
    pool.map(call_script, scripts)
    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
