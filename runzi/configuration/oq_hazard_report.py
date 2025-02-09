import os
import stat
from pathlib import PurePath

import runzi.execute.oq_hazard_report_task
from runzi.automation.scaling.hazard_output_helper import HazardOutputHelper
from runzi.automation.scaling.local_config import CLUSTER_MODE, WORK_PATH, EnvMode
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.automation.scaling.toshi_api import ToshiApi


def build_hazard_report_tasks(subtask_arguments, toshi_api: ToshiApi):

    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.oq_hazard_report_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    # file_generators = []
    # for hazard_soln_id in subtask_arguments['hazard_ids']:
    #     file_generators.append(get_output_file_id(toshi_api, input_id)) #for file by file ID

    # source_solutions = download_files(toshi_api, chain(*file_generators), str(WORK_PATH), overwrite=False,
    #     skip_download=(CLUSTER_MODE == EnvMode['AWS']))

    hazard_helper = HazardOutputHelper(toshi_api)

    hazard_soln_ids = []
    if subtask_arguments.get('gt_ids'):
        for gt_id in subtask_arguments.get('gt_ids'):
            hazard_soln_ids += list(hazard_helper.get_hazard_ids_from_gt(gt_id).keys())
    if subtask_arguments.get('hazard_ids'):
        hazard_soln_ids += subtask_arguments.get('hazard_ids')

    use_hdf5 = subtask_arguments['use_hdf5']

    # remove duplicates
    hazard_soln_ids = list(dict.fromkeys(hazard_soln_ids))
    if use_hdf5:
        hazard_solutions = hazard_helper.download_hdf(hazard_soln_ids, str(WORK_PATH))
    else:  # create a dummy dict
        hazard_solutions = {}
        for hazard_id in hazard_soln_ids:
            hazard_solutions[hazard_id] = dict(hazard_id=hazard_id)

    for hdf_id, hazard_info in hazard_solutions.items():

        task_count += 1

        if use_hdf5:
            task_arguments = dict(file_id=hdf_id, file_path=hazard_info['filepath'], hazard_id=hazard_info['hazard_id'])
        else:
            task_arguments = dict(hazard_id=hazard_info['hazard_id'])

        job_arguments = dict(task_id=task_count, use_hdf5=subtask_arguments['use_hdf5'])

        if CLUSTER_MODE == EnvMode['AWS']:
            pass
            # job_name = f"Runzi-automation-subduction_inversions-{task_count}"
            # config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

            # yield get_ecs_job_config(job_name, solution_info['id'], config_data,
            #     toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
            #     task_module=inversion_solution_builder_task.__name__,
            #     time_minutes=int(max_inversion_time), memory=30720, vcpu=4)

        else:
            # write a config
            task_factory.write_task_config(task_arguments, job_arguments)
            script = task_factory.get_task_script()

            script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
            with open(script_file_path, 'w') as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
