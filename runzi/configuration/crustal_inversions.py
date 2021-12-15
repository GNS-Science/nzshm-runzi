import os
import pwd
import itertools
import stat
import json
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool
import boto3

import datetime as dt

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids

from runzi.execute import inversion_solution_builder_task
from runzi.util.aws import get_ecs_job_config

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, S3_REPORT_BUCKET, CLUSTER_MODE, EnvMode)

INITIAL_GATEWAY_PORT = 26533 #set this to ensure that concurrent scheduled tasks won't clash
#JAVA_THREADS = 4

if CLUSTER_MODE == EnvMode['AWS']:
    WORK_PATH='/WORKING'

def build_crustal_tasks(general_task_id, rupture_sets, args):
    task_count = 0

    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(OPENSHA_ROOT, WORK_PATH, inversion_solution_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START)

    for (rid, rupture_set_info) in rupture_sets.items():
        for (_round, completion_energy, max_inversion_time,
                mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
                slip_rate_weight, slip_uncertainty_scaling_factor,
                slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
                mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
                seismogenic_min_mag,
                selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
                non_negativity_function, perturbation_function,
                deformation_model,
                scaling_relationship, scaling_recalc_mag,
                paleo_rate_constraint_weight, paleo_rate_constraint,
                paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight
                )\
            in itertools.product(
                args['rounds'], args['completion_energies'], args['max_inversion_times'],
                args['mfd_equality_weights'], args['mfd_inequality_weights'], args['slip_rate_weighting_types'],
                args['slip_rate_weights'], args['slip_uncertainty_scaling_factors'],
                args['slip_rate_normalized_weights'],  args['slip_rate_unnormalized_weights'],
                args['mfd_mag_gt_5_sans'], args['mfd_mag_gt_5_tvz'],
                args['mfd_b_values_sans'], args['mfd_b_values_tvz'], args['mfd_transition_mags'],
                args['seismogenic_min_mags'],
                args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
                args['non_negativity_function'], args['perturbation_function'],
                args['deformation_models'],
                args['scaling_relationships'], args['scaling_recalc_mags'],
                args['paleo_rate_constraint_weights'], args['paleo_rate_constraints'],
                args['paleo_probability_models'], args['paleo_parent_rate_smoothness_constraint_weights']
                ):

            task_count +=1

            task_arguments = dict(
                round = _round,
                config_type = 'crustal',
                deformation_model=deformation_model,
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
                seismogenic_min_mag=seismogenic_min_mag,
                mfd_mag_gt_5_sans=mfd_mag_gt_5_sans,
                mfd_mag_gt_5_tvz=mfd_mag_gt_5_tvz,
                mfd_b_value_sans=mfd_b_value_sans,
                mfd_b_value_tvz=mfd_b_value_tvz,
                mfd_transition_mag=mfd_transition_mag,

                #New config arguments for Simulated Annealing ...
                selection_interval_secs=selection_interval_secs,
                threads_per_selector=threads_per_selector,
                averaging_threads=averaging_threads,
                averaging_interval_secs=averaging_interval_secs,
                non_negativity_function=non_negativity_function,
                perturbation_function=perturbation_function,

                scaling_relationship=scaling_relationship,
                scaling_recalc_mag=scaling_recalc_mag,

                #New Paleo Args...
                paleo_rate_constraint_weight=paleo_rate_constraint_weight,
                paleo_rate_constraint=paleo_rate_constraint,
                paleo_probability_model=paleo_probability_model,
                paleo_parent_rate_smoothness_constraint_weight=paleo_parent_rate_smoothness_constraint_weight
                )

            job_arguments = dict(
                task_id = task_count,
                java_threads = int(threads_per_selector) * int(averaging_threads), # JAVA_THREADS,
                jvm_heap_max = JVM_HEAP_MAX,
                java_gateway_port=task_factory.get_next_port(),
                working_path=str(WORK_PATH),
                root_folder=OPENSHA_ROOT,
                general_task_id=general_task_id,
                use_api = USE_API,
                )

            if CLUSTER_MODE == EnvMode['AWS']:

                job_name = f"Runzi-automation-crustal_inversions-{task_count}"
                config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

                yield get_ecs_job_config(job_name, rupture_set_info['id'], config_data,
                    toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                    task_module=inversion_solution_builder_task.__name__,
                    time_minutes=int(max_inversion_time), memory=30720, vcpu=4)

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

# if __name__ == "__main__":

#     t0 = dt.datetime.utcnow()

#     # If you wish to override something in the main config, do so here ..
#     # WORKER_POOL_SIZE = 3
#     WORKER_POOL_SIZE = 1
#     JVM_HEAP_MAX = 30
#     JAVA_THREADS = 4
#     #USE_API = False

#     INITIAL_GATEWAY_PORT = 26533 #set this to ensure that concurrent scheduled tasks won't clash

#     #If using API give this task a descriptive setting...
#     TASK_TITLE = "MModular Inversions: Coulomb D90 Geologic; Simplified Scaling Upper bound: TEST ECS"
#     TASK_DESCRIPTION = """targeted sans_TVZ b/N values"""

#     GENERAL_TASK_ID = None

#     headers={"x-api-key":API_KEY}
#     toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

#     #get input files from API
#     file_id = "RmlsZTozMDMuMEJCOVVY" #PROD D90 Coulomb
#     # file_id = "RmlsZTo4NTkuMDM2Z2Rw" #PROD 2010_Coulomb
#     # file_id = "RmlsZTozODEuMFJxVTI2" #TEST D90
#     file_id = "RmlsZToxNTg3LjBuVm9GdA==" #TEST D90 full coulomb
#     """
#     CHOOSE ONE OF:

#      - file_generator = get_output_file_id(toshi_api, file_id)
#      - file_generator = get_output_file_ids(general_api, upstream_task_id)
#     """
#     #for a single rupture set, pass a valid FileID

#     file_generator = get_output_file_id(toshi_api, file_id) #for file by file ID
#     rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

#     args = dict(
#         rounds = [str(x) for x in range(1)],
#         completion_energies = ['0.0'], # 0.005]
#         max_inversion_times = ['3'], #8*60,] #3*60,]  #units are minutes
#         #max_inversion_times.reverse()

#         deformation_models = ['FAULT_MODEL',], # GEOD_NO_PRIOR_UNISTD_2010_RmlsZTo4NTkuMDM2Z2Rw, 'GEOD_NO_PRIOR_UNISTD_D90_RmlsZTozMDMuMEJCOVVY',
#         mfd_mag_gt_5_sans = [2.0, 5.0],
#         mfd_mag_gt_5_tvz = [0.2],
#         mfd_b_values_sans = [0.97, 0.86],
#         mfd_b_values_tvz = [0.97],
#         mfd_transition_mags = [7.85],

#         seismogenic_min_mags  = ['7.0'],
#         mfd_equality_weights = [1e4, 1.3],
#         mfd_inequality_weights = [0],

#         slip_rate_weighting_types = ['BOTH'], #NORMALIZED_BY_SLIP_RATE', UNCERTAINTY_ADJUSTED', BOTH

#         #these are used for UNCERTAINTY_ADJUSTED
#         slip_rate_weights = ['', ],# 1e5, 1e4, 1e3, 1e2]
#         slip_uncertainty_scaling_factors = ['',],#2,]

#         #these are used for BOTH, NORMALIZED and UNNORMALIZED
#         slip_rate_normalized_weights = ['1e4', '1e3'],
#         slip_rate_unnormalized_weights = ['1e4'],

#         #New modular inversion configurations
#         selection_interval_secs = ['1'],
#         threads_per_selector = ['4'],
#         averaging_threads = ['4'],
#         averaging_interval_secs = ['30'],
#         non_negativity_function = ['TRY_ZERO_RATES_OFTEN'], # TRY_ZERO_RATES_OFTEN,  LIMIT_ZERO_RATES, PREVENT_ZERO_RATES
#         perturbation_function = ['EXPONENTIAL_SCALE'], # UNIFORM_NO_TEMP_DEPENDENCE, EXPONENTIAL_SCALE;

#         #Scaling Relationships
#         scaling_relationships=['SMPL_NZ_INT_UP'], #'SMPL_NZ_INT_LW', 'SMPL_NZ_INT_UP'],
#         scaling_recalc_mags=['True']

#     )
#     args_list = []
#     for key, value in args.items():
#         args_list.append(dict(k=key, v=value))

#     if USE_API:
#         #create new task in toshi_api
#         gt_args = CreateGeneralTaskArgs(
#             agent_name=pwd.getpwuid(os.getuid()).pw_name,
#             title=TASK_TITLE,
#             description=TASK_DESCRIPTION
#             )\
#             .set_argument_list(args_list)\
#             .set_subtask_type('INVERSION')\
#             .set_model_type('CRUSTAL')
#         GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

#     print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

#     if CLUSTER_MODE == EnvMode['AWS']:
#         batch_client = boto3.client(
#             service_name='batch',
#             region_name='us-east-1',
#             endpoint_url='https://batch.us-east-1.amazonaws.com')

#     scripts = []
#     for script_file_or_config in build_crustal_tasks(GENERAL_TASK_ID, rupture_sets, args):
#         scripts.append(script_file_or_config)

#     if CLUSTER_MODE == EnvMode['LOCAL']:
#         def call_script(script_or_config):
#             print("call_script with:", script_or_config)
#             check_call(['bash', script_or_config])

#         print('task count: ', len(scripts))
#         print('worker count: ', WORKER_POOL_SIZE)
#         pool = Pool(WORKER_POOL_SIZE)
#         pool.map(call_script, scripts)
#         pool.close()
#         pool.join()

#     elif CLUSTER_MODE == EnvMode['AWS']:
#         for script_or_config in scripts:
#             #print('AWS_TIME!: ', script_or_config)
#             res = batch_client.submit_job(**script_or_config)
#             print(res)
#     else:
#         for script_or_config in scripts:
#             check_call(['qsub', script_or_config])

#     print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
#     print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
