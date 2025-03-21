import os
import stat
from pathlib import PurePath

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_URL,
    BUILD_PLOTS,
    CLUSTER_MODE,
    FATJAR,
    HACK_FAULT_MODEL,
    JAVA_THREADS,
    JVM_HEAP_MAX,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    REPORT_LEVEL,
    S3_REPORT_BUCKET,
    S3_URL,
    USE_API,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.execute import inversion_diags_report_task
from runzi.util.aws import get_ecs_job_config

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
MAX_JOB_TIME_SECS = 60 * 30  # Change this soon


def generate_tasks_or_configs(general_task_id, solutions):
    work_path = '/WORKING' if CLUSTER_MODE == EnvMode['AWS'] else WORK_PATH
    task_count = 0

    factory_class = get_factory(CLUSTER_MODE)
    task_factory = factory_class(
        OPENSHA_ROOT,
        work_path,
        inversion_diags_report_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=work_path,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for sid, solution_info in solutions.items():

        task_count += 1

        # get FM name
        fault_model = solution_info['info'].get('fault_model', "")
        if HACK_FAULT_MODEL:
            fault_model = HACK_FAULT_MODEL

        task_arguments = dict(
            file_id=str(solution_info['id']),
            file_path=solution_info['filepath'],
            fault_model=fault_model,
        )
        # print(task_arguments)

        job_arguments = dict(
            task_id=task_count,
            # round = round,
            java_threads=JAVA_THREADS,
            java_gateway_port=task_factory.get_next_port(),
            working_path=str(work_path),
            root_folder=OPENSHA_ROOT,
            general_task_id=general_task_id,
            use_api=USE_API,
            build_mfd_plots=BUILD_PLOTS,
            build_report_level=REPORT_LEVEL,
        )

        if CLUSTER_MODE == EnvMode['AWS']:
            del job_arguments['root_folder']
            job_name = f"Runzi-automation-inversion_diagnostic-{task_count}"
            config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

            yield get_ecs_job_config(
                job_name,
                solution_info['id'],
                config_data,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=inversion_diags_report_task.__name__,
                time_minutes=int(MAX_JOB_TIME_SECS),
                memory=30720,
                vcpu=4,
            )

        else:
            # write a config
            task_factory.write_task_config(task_arguments, job_arguments)

            script = task_factory.get_task_script()

            script_file_path = PurePath(work_path, f"task_{task_count}.sh")
            with open(script_file_path, 'w') as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
            # return


# if __name__ == "__main__":
#     t0 = dt.datetime.utcnow()

#     GENERAL_TASK_ID = None
#     # If you wish to override something in the main config, do so here ..
#     WORKER_POOL_SIZE = 3
#     JVM_HEAP_MAX = 12
#     JAVA_THREADS = 4
#     # USE_API = True #to read the ruptset form the API


#     #If using API give this task a descriptive setting...
#     TASK_TITLE = "Inversion diags"
#     TASK_DESCRIPTION = """
#     """

#     def call_script(script_name):
#         print("call_script with:", script_name)
#         if CLUSTER_MODE:
#             check_call(['qsub', script_name])
#         else:
#             check_call(['bash', script_name])

#     headers={"x-api-key":API_KEY}
#     file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

#     BUILD_PLOTS = True
#     REPORT_LEVEL = 'DEFAULT' # None, 'LIGHT', 'DEFAULT', 'FULL'

#     pool = Pool(WORKER_POOL_SIZE)
#     for inversion_task_id in ["R2VuZXJhbFRhc2s6NDY5NkdnUWpj"]:
# #"R2VuZXJhbFRhc2s6Mjc4OXphVmN2"]: #, "R2VuZXJhbFRhc2s6MjY4M1FGajVh"]:
#         #get input files from API
#         file_generator = get_output_file_ids(file_api, inversion_task_id) #
#         solutions = download_files(file_api, file_generator, str(work_path), overwrite=False, skip_existing=False)

#         print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

#         #print('SOLUTIONS', solutions)
#         scripts = []
#         for script_file in generate_tasks_or_configs(GENERAL_TASK_ID, solutions):
#             print('scheduling: ', script_file)
#             scripts.append(script_file)

#         print('task count: ', len(scripts))
#         pool.map(call_script, scripts)

#     print('worker count: ', WORKER_POOL_SIZE)

#     pool.close()
#     pool.join()

#     print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
