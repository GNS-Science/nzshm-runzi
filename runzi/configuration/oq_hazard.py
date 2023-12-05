import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath
from dataclasses import asdict

import datetime as dt
from dateutil.tz import tzutc

from itertools import chain

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType

from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config, BatchEnvironmentSetting

import runzi.execute.openquake.oq_hazard_task
from runzi.execute.openquake.util import get_decomposed_logic_trees

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode, S3_URL, S3_REPORT_BUCKET)

HAZARD_MAX_TIME = 48*60 #minutes

# SPLIT_SOURCE_BRANCHES = True
# SPLIT_TRUNCATION = 1 # set to None if you want all the split jobs, this is just for testing
# GRANULAR = True

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
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

DEFAULT_CONFIG = dict(
    general = dict(
        random_seed = 25,
        calculation_mode = 'classical',
        ps_grid_spacing = 30,
    ),
    logic_tree = dict(
        number_of_logic_tree_samples = 0,
    ),
    erf = dict(
        rupture_mesh_spacing = 5,
        width_of_mfd_bin = 0.1,
        complex_fault_mesh_spacing = 10.0,
        area_source_discretization = 10.0,
    ),
    site_params = dict(
        reference_vs30_type = 'measured',
    ),
    calculation = dict(
        investigation_time = 1.0,
        truncation_level = 4,
        maximum_distance = {'Active Shallow Crust': [(4.0, 0), (5.0, 100.0), (6.0, 200.0), (9.5, 300.0)],
                            'Subduction Interface': [(5.0, 0), (6.0, 200.0), (10, 500.0)],
                            'Subduction Intraslab': [(5.0, 0), (6.0, 200.0), (10, 500.0)]}
    ),
    output = dict(
        individual_curves = 'true',
    ),
)

def build_task(task_arguments, job_arguments, task_id, extra_env):

    if CLUSTER_MODE == EnvMode['AWS']:
        job_name = f"Runzi-automation-oq-hazard-{task_id}"
        config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

        if BIGGER_LEVER:
            return get_ecs_job_config(job_name,
                'N/A', config_data,
                toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.openquake.oq_hazard_task.__name__,
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

def update_arguments(dict1, dict2):

    for name, table in dict2.items():
        if dict2.get(name):
            for k, v in table.items():
                dict1[name][k] = v
        else:
            dict1[name] = table

    # return dict1



def build_hazard_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, subtask_arguments ):

    def unpack_keys(d):
        keys = []
        for k1,v in d.items():
            for k2 in v.keys():
                keys.append((k1, k2))
        return keys

    def unpack_values(d):
        for v in d.values():
            for v2 in v.values():
                yield v2

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]

    iterate = subtask_arguments["config_iterate"]
    # iterate["site_params"] = dict() if not iterate.get("site_params") else iterate["site_params"]
    # iterate["site_params"]["vs30"] = (
    #     subtask_arguments["vs30"] if isinstance(subtask_arguments["vs30"], list) else [subtask_arguments["vs30"]]
    # )
    vs30s = subtask_arguments["vs30"] if isinstance(subtask_arguments["vs30"], list) else [subtask_arguments["vs30"], ]
    iter_keys = unpack_keys(iterate)
    task_count = 0
    for vs30 in vs30s:
        for iter_values in itertools.product(*unpack_values(iterate)):

                task_arguments = dict(
                    gmcm_logic_tree=subtask_arguments["gmcm_logic_tree"],
                    model_type = model_type.name,
                    intensity_spec = subtask_arguments["intensity_spec"],
                    location_list = subtask_arguments["location_list"],
                    vs30 = vs30,
                    disagg_conf = subtask_arguments["disagg_conf"],
                )

                task_arguments["oq"] = DEFAULT_CONFIG  # default openquake config
                # overwrite with user specifiction
                update_arguments(task_arguments["oq"], subtask_arguments["config_scalar"])
                iter_dict = dict()
                for k, v in zip(iter_keys, iter_values):
                    iter_dict[k[0]] = {k[1]: v}
                update_arguments(task_arguments["oq"], iter_dict)
                description = ": ".join((subtask_arguments["general"].get("title"), subtask_arguments["general"].get("description")))
                update_arguments(task_arguments["oq"], {"general": {"description": description}})

                print('')
                print('task arguments MERGED')
                print('==========================')
                print(task_arguments)
                print('==========================')
                print('')

                for srm_logic_tree in get_decomposed_logic_trees(
                    subtask_arguments['srm_logic_tree'], subtask_arguments['slt_decomposition']
                    ):

                    task_count +=1
                    job_arguments = dict(
                        task_id = task_count,
                        general_task_id = general_task_id,
                        use_api = USE_API,
                        )
                    if subtask_arguments['slt_decomposition'] == 'composite':
                        task_arguments['srm_flat_logic_tree'] = asdict(srm_logic_tree)
                    else:
                        task_arguments['srm_logic_tree'] = asdict(srm_logic_tree) # serialize logic tree object?
                    yield build_task(task_arguments, job_arguments, task_count, extra_env)


            # if not (SPLIT_SOURCE_BRANCHES or GRANULAR):
            #     yield build_task(task_arguments, job_arguments, task_count, extra_env)
            #     continue

            # if GRANULAR:
            #     #SMALLEST BUIL
            #     pass
            #     granular_id = 0
                # for ltb in get_granular_logic_tree_branches(logic_tree_permutations):
            #         # print(f'granular ltb {ltb} task_id {job_arguments["task_id"]}')
            #         # task_arguments['split_source_branches'] = SPLIT_SOURCE_BRANCHES
            #         # task_arguments['split_source_id'] = split_id
            #         granular_id +=1
            #         new_task_id = job_arguments['task_id'] * granular_id
            #         new_permuations = [{'tag': 'GRANULAR', 'weight': 1.0, 'permute': [{'group': 'ALL', 'members': [ltb._asdict()] }]}]
            #         task_arguments['logic_tree_permutations'] = new_permuations
            #         task_arguments['split_source_branches'] = False
            #         # # job_arguments['task_id'] = new_task_id
            #         # #TODO replace logic_tree_permuations here!
            #         # print('new_task_id', new_task_id)
            #         yield build_task(task_arguments, job_arguments, new_task_id, extra_env)

            #     continue

            # if SPLIT_SOURCE_BRANCHES:
            #     split_range = SPLIT_TRUNCATION if SPLIT_TRUNCATION else len(ltbs) # how many split  jobs to actually run
            #     print(f'logic_tree_permutations: {logic_tree_permutations}')
            #     ltbs = list(get_logic_tree_branches(logic_tree_permutations))
            #     for split_id in range(split_range):
            #         print(f'split_id {split_id} task_idL {job_arguments["task_id"]}')
            #         task_arguments['split_source_branches'] = SPLIT_SOURCE_BRANCHES
            #         task_arguments['split_source_id'] = split_id
            #         new_task_id = job_arguments['task_id'] * (split_id +1)
            #         # job_arguments['task_id'] = new_task_id
            #         yield build_task(task_arguments, job_arguments, new_task_id, extra_env)