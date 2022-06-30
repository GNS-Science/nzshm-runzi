import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath

import datetime as dt
from dateutil.tz import tzutc

from itertools import chain

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType

from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config, BatchEnvironmentSetting
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

import runzi.execute.oq_hazard_task
from runzi.execute.util import get_logic_tree_branches, get_granular_logic_tree_branches

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode, S3_URL, S3_REPORT_BUCKET)

HAZARD_MAX_TIME = 240 #minutes

SPLIT_SOURCE_BRANCHES = True
SPLIT_TRUNCATION = 1 # set to None if you want all the split jobs, this is just for testing
GRANULAR = True

##BL_CONF_0 = dict( job_def="BigLever_32GB_8VCPU_JD", job_queue="BigLever_32GB_8VCPU_JQ", mem=30000, cpu=8)
BL_CONF_1 = dict( job_def="BigLever_32GB_8VCPU_v2_JD", job_queue="BigLever_32GB_8VCPU_v2_JQ", mem=30000, cpu=8)

BL_CONF_0 = dict( job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=380000, cpu=48) #r5.12xlarge or similar
BL_CONF_16_120 = dict( job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=120000, cpu=16) #r5.12xlarge or similar
BL_CONF_32_60 = dict( job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=60000, cpu=32) #
BL_CONF_16_30 = dict( job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=30000, cpu=16) #
BL_CONF_8_20 = dict( job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=20000, cpu=8) #
BL_CONF_32_120 = dict( job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=120000, cpu=32) #r5.12xlarge or similar

BIGGER_LEVER = True # FALSE uses fargate
BIGGER_LEVER_CONF = BL_CONF_1 #BL_CONF_32_120

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

def build_task(task_arguments, job_arguments, task_id, extra_env):

    if CLUSTER_MODE == EnvMode['AWS']:
        job_name = f"Runzi-automation-oq-hazard-{task_id}"
        config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

        if BIGGER_LEVER:
            return get_ecs_job_config(job_name,
                'N/A', config_data,
                toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME),
                memory=BIGGER_LEVER_CONF["mem"],
                vcpu=BIGGER_LEVER_CONF["cpu"],
                job_definition=BIGGER_LEVER_CONF["job_def"], # "BigLeverOnDemandEC2-JD", # "BiggerLever-runzi-openquake-JD", #"getting-started-job-definition-jun7",
                job_queue=BIGGER_LEVER_CONF["job_queue"],
                extra_env = extra_env,
                use_compression = True)
        else:
            return get_ecs_job_config(job_name,
                'N/A', config_data,
                toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4,
                job_definition="Fargate-runzi-openquake-JD",
                extra_env = extra_env,
                use_compression = True)

    else:
        #write a config
        task_factory.write_task_config(task_arguments, job_arguments)
        script = task_factory.get_task_script()

        script_file_path = PurePath(WORK_PATH, f"task_{task_id}.sh")
        with open(script_file_path, 'w') as f:
            f.write(script)

        #make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        return str(script_file_path)


def build_hazard_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, subtask_arguments ):
    task_count = 0

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2")
    ]

    for (config_archive_id,
        logic_tree_permutations,
        intensity_spec,
        vs30,
        location_code,
        disagg_conf,
        rupture_mesh_spacing,
        ps_grid_spacing
        )\
        in itertools.product(
            subtask_arguments["config_archive_ids"],
            subtask_arguments['logic_tree_permutations'],
            subtask_arguments['intensity_specs'],
            subtask_arguments['vs30s'],
            subtask_arguments['location_codes'],
            subtask_arguments['disagg_confs'],
            subtask_arguments['rupture_mesh_spacings'],
            subtask_arguments['ps_grid_spacings']
            ):

            task_count +=1

            task_arguments = dict(

                # nrml_id = nrml_info['id'], #One NRML, what about multiple NRMLs
                # file_name = nrml_info['info']['file_name'],
                config_archive_id = config_archive_id, #File archive object
                #upstream_general_task=source_gt_id,
                model_type = model_type.name,
                logic_tree_permutations = logic_tree_permutations,
                intensity_spec = intensity_spec,
                vs30 = vs30,
                location_code = location_code,
                disagg_conf = disagg_conf,
                rupture_mesh_spacing = rupture_mesh_spacing,
                ps_grid_spacing = ps_grid_spacing
                )

            print('')
            print('task arguments MERGED')
            print('==========================')
            print(task_arguments)
            print('==========================')
            print('')

            job_arguments = dict(
                task_id = task_count,
                general_task_id = general_task_id,
                use_api = USE_API,
                )

            if not (SPLIT_SOURCE_BRANCHES or GRANULAR):
                yield build_task(task_arguments, job_arguments, task_count, extra_env)
                continue

            if GRANULAR:
                #SMALLEST BUIL
                pass
                granular_id = 0
                for ltb in get_granular_logic_tree_branches(logic_tree_permutations):
                    # print(f'granular ltb {ltb} task_id {job_arguments["task_id"]}')
                    # task_arguments['split_source_branches'] = SPLIT_SOURCE_BRANCHES
                    # task_arguments['split_source_id'] = split_id
                    granular_id +=1
                    new_task_id = job_arguments['task_id'] * granular_id
                    new_permuations = [{'tag': 'GRANULAR', 'weight': 1.0, 'permute': [{'group': 'ALL', 'members': [ltb._asdict()] }]}]
                    task_arguments['logic_tree_permutations'] = new_permuations
                    task_arguments['split_source_branches'] = False
                    # # job_arguments['task_id'] = new_task_id
                    # #TODO replace logic_tree_permuations here!
                    # print('new_task_id', new_task_id)
                    yield build_task(task_arguments, job_arguments, new_task_id, extra_env)

                continue

            if SPLIT_SOURCE_BRANCHES:
                split_range = SPLIT_TRUNCATION if SPLIT_TRUNCATION else len(ltbs) # how many split  jobs to actually run
                print(f'logic_tree_permutations: {logic_tree_permutations}')
                ltbs = list(get_logic_tree_branches(logic_tree_permutations))
                for split_id in range(split_range):
                    print(f'split_id {split_id} task_idL {job_arguments["task_id"]}')
                    task_arguments['split_source_branches'] = SPLIT_SOURCE_BRANCHES
                    task_arguments['split_source_id'] = split_id
                    new_task_id = job_arguments['task_id'] * (split_id +1)
                    # job_arguments['task_id'] = new_task_id
                    yield build_task(task_arguments, job_arguments, new_task_id, extra_env)