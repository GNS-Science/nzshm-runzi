import os
import pwd
import itertools
import stat
from dataclasses import asdict
from pathlib import PurePath

import numpy as np

from nzshm_model.source_logic_tree import SourceLogicTree
import toshi_hazard_store

from .util import unpack_values, unpack_keys, update_oq_args
from .oq_hazard import DEFAULT_HAZARD_CONFIG


from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType, ModelType, CreateGeneralTaskArgs

from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config, BatchEnvironmentSetting

import runzi.execute.openquake.oq_hazard_task

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode, S3_URL, S3_REPORT_BUCKET)

HAZARD_MAX_TIME = 20 #minutes

BL_CONF_1 = dict( job_def="BigLever_32GB_8VCPU_v2_JD", job_queue="BigLever_32GB_8VCPU_v2_JQ", mem=30000, cpu=8)
BL_CONF_2 = dict( job_def="BigLever_32GB_8VCPU_v2_JD", job_queue="BigLever_16GB_4VCPU_JQ", mem=15000, cpu=4)
BIGGER_LEVER = True # FALSE uses fargate
BIGGER_LEVER_CONF = BL_CONF_2 #BL_CONF_32_120

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

DEFAULT_DISAGG_CONFIG = DEFAULT_HAZARD_CONFIG.copy()
DEFAULT_DISAGG_CONFIG["calculation_mode"] = "disaggregation"
DEFAULT_DISAGG_CONFIG["disagg"] = dict(
    max_sites_disagg = 1,
    mag_bin_width = 0.1999,
    distance_bin_width = 10, 
    coordinate_bin_width = 5,
    num_epsilon_bins = 16, 
    disagg_outputs = "TRT Mag Dist Mag_Dist TRT_Mag_Dist_Eps",
    disagg_bin_edges = {'dist': [0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 140.0, 180.0, 220.0, 260.0, 320.0, 380.0, 500.0]},
)

GT_COUNTER = 0

def compute_hazard_at_poe(levels, values, poe, inv_time):
    
    rp = -inv_time / np.log(1 - poe)
    haz = np.exp(np.interp(np.log(1 / rp), np.flip(np.log(values)), np.flip(np.log(levels))))
    return haz

def get_target_level(
    hazard_model_id,
    location,
    vs30,
    imt,
    agg,
    poe,
    inv_time,
):

    hc = next(toshi_hazard_store.query_v3.get_hazard_curves([location], [vs30], [hazard_model_id], [imt], [agg]))
    levels = []
    hazard_vals = []
    for v in hc.values:
        levels.append(float(v.lvl))
        hazard_vals.append(float(v.val)) 

    return compute_hazard_at_poe(levels, hazard_vals, poe, inv_time)


#TODO: using custom function here to also retrive the nrlz from the logic tree.
# Once LT has it's onwn class that includes GMCM, we can unify the LT functions
# def get_granular_logic_tree_branches_wnrlz(ltb_groups):

#     for group in ltb_groups: #dict in list (len = 1)
#         for fault_system in group['permute']:
#             nrlz = fault_system['nrlz']
#             for member in fault_system['members']:
#                 member['nrlz'] = nrlz
#                 yield member


# def get_lt_branches(logic_trees):
#     """
#     Get branch information for logic tree without combinations across fault system logic trees.

#     Parameters
#     ----------
#     logic_trees: list
#         logic tree definition
    
#     Returns
#     -------
#     lt_branches: List[dict]
#         each dict contains 'source_ids' and 'nrlz' of logic tree branch
#     """

#     lt_branches = []
#     for logic_tree in logic_trees: 
#         # print(logic_tree)
#         for ltb in get_granular_logic_tree_branches_wnrlz(logic_tree):
#             # print(ltb)
#             source_ids = [v for k,v in ltb.items() if '_id' in k]
#             lt_branches.append({'source_ids': source_ids, 'nrlz': ltb['nrlz']})

#     return lt_branches

# def get_disagg_configs(gt_config, logic_trees):
#     """
#     Get a configuration used for launching oq-engine disaggregations for
#     every branch of a logic tree without forming combinations between fault system logic trees.

#     Parameters
#     ----------
#     gt_config : dict
#         contains information about location, vs30, poe, etc for disaggregation
#         {
#         'location':str, (could be site_code or encoded lat~lon)
#         'poe':float (0-1),
#         'vs30':float,
#         'imt': str,
#         'inv_time': float,
#         'agg': str,
#         'hazard_model_id': str
#         }
#     logic_trees : list
#         logic tree definition

#     Returns
#     -------
#     list
#         Format matches output from THP --deagg CONFIG but does not contain 'source_tree_hazid' key
#     """

#     configs = gt_config.copy()
#     if location_by_id(configs['location']):
#         configs['site_code'] = configs['location']
#         configs['site_name'] = location_by_id(configs['location'])['name']
#         resolution = 0.001
#         lat = location_by_id(configs['location'])['latitude']
#         lon = location_by_id(configs['location'])['longitude']
#         location = CodedLocation(lat, lon, resolution).code
#         configs['location'] = location
#     elif '~' in configs['location']:
#         location = configs['location']
#     else:
#         raise Exception('location must be valid site_code or coded location string')

#     configs['target_level'] = get_target_level(gt_config, location)
#     configs['deagg_specs'] = get_lt_branches(logic_trees)

#     return [configs]


def build_task(task_arguments, job_arguments, task_id, extra_env):

    if CLUSTER_MODE == EnvMode['AWS']:
        job_name = f"Runzi-automation-oq-disagg-{task_id}"
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
                task_module=runzi.execute.openquake.oq_hazard_task.__name__,
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


def new_general_task(gt_arguments, title, description, subtask_type, model_type):

    if not USE_API:
        global GT_COUNTER
        GT_COUNTER += 1
        return f'none_{GT_COUNTER}'
    
    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    args_list = []
    for key, value in gt_arguments.items():
        args_list.append(dict(k=key, v=value))

    if USE_API:

        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=title,
            description=description,
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(subtask_type)\
            .set_model_type(model_type)

        gt_id = toshi_api.general_task.create_task(gt_args)

    return gt_id


def build_disagg_tasks(subtask_type: SubtaskType, model_type: ModelType, args):
    task_count = 0
    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]

    iterate = args["config_iterate"]
    iter_keys = unpack_keys(iterate)
    task_count = 0
    for location, vs30, poe, imt, agg in itertools.product(
        args["location_codes"],
        args["vs30s"],
        args["poes"],
        args["imts"],
        args["aggs"],
    ):
        target_level = get_target_level(
            args["hazard_model_id"],
            location,
            vs30,
            imt,
            agg,
            poe,
            args["inv_time"],
        )

        for iter_values in itertools.product(*unpack_values(iterate)):
            task_arguments = dict(
                    gmcm_logic_tree=args["gmcm_logic_tree"],
                    model_type = model_type.name,
                    location = location,
                    vs30 = vs30,
                    imt = imt,
                    agg = agg,
                    poe = poe,
                    inv_time = args["inv_time"],
                    level = target_level,
                )
            task_arguments["oq"] = DEFAULT_DISAGG_CONFIG # default openquake config
            # overwrite with user specifiction
            description = ": ".join(
                (args["general"].get("title"), args["general"].get("description"))
            )
            update_oq_args(
                task_arguments["oq"], args["config_scalar"], iter_keys, iter_values, description
            )

            print('')
            print('task arguments MERGED')
            print('==========================')
            print(task_arguments)
            print('==========================')
            print('')

            # This is done at the config level only because we use the GT to keep track a a single disaggegation (for
            # all logic tree brances). This would normally live at the run level
            gt_id = new_general_task(
                task_arguments,
                args["general"].get("title"),
                args["general"].get("description"),
                subtask_type,
                model_type,
            )

            # iterate over every branch of the logic tree to create a task
            new_gt_id = None
            for branch in args['srm_logic_tree']:
                if not new_gt_id:
                    new_gt_id = gt_id
                slt = SourceLogicTree.from_branches([branch])

                task_count +=1
                job_arguments = dict(
                    task_id = task_count,
                    general_task_id = gt_id,
                    use_api = USE_API,
                    )
                task_arguments['srm_logic_tree'] = asdict(slt) 
                yield build_task(task_arguments, job_arguments, task_count, extra_env), gt_id

