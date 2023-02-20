import os
import pwd
import itertools
import stat
import boto3
from pathlib import PurePath

import datetime as dt
from dateutil.tz import tzutc
from typing import Iterable

import numpy as np

from nzshm_common.location.location import LOCATIONS_BY_ID, LOCATIONS_SRWG214_BY_ID
from nzshm_common.location.code_location import CodedLocation
# from toshi_hazard_store.query_v3 import get_hazard_curves
import toshi_hazard_store


from itertools import chain

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType

from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config, BatchEnvironmentSetting

import runzi.execute.openquake.oq_hazard_task

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode, S3_URL, S3_REPORT_BUCKET)

HAZARD_MAX_TIME = 20 #minutes

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

def compute_hazard_at_poe(levels, values, poe, inv_time):

    rp = -inv_time / np.log(1 - poe)
    haz = np.exp(np.interp(np.log(1 / rp), np.flip(np.log(values)), np.flip(np.log(levels))))
    return haz

def get_target_level(gt_config, location):

    hazard_model_id = gt_config['hazard_model_id']
    poe = gt_config['poe']
    inv_time = gt_config['inv_time']
    agg = gt_config['agg']
    imt = gt_config['imt']
    vs30 = gt_config['vs30']
    hc = next(toshi_hazard_store.query_v3.get_hazard_curves([location], [vs30], [hazard_model_id], [imt], [agg]))
    levels = []
    hazard_vals = []
    for v in hc.values:
        levels.append(v.lvl)
        hazard_vals.append(v.val) 

    return compute_hazard_at_poe(levels, hazard_vals, poe, inv_time)


#TODO: using custom function here to also retrive the nrlz from the logic tree.
# Once LT has it's onwn class that includes GMCM, we can unify the LT functions
def get_granular_logic_tree_branches_wnrlz(ltb_groups):

    for group in ltb_groups: #dict in list (len = 1)
        for fault_system in group['permute']:
            nrlz = fault_system['nrlz']
            for member in fault_system['members']:
                member['nrlz'] = nrlz
                yield member


def get_lt_branches(logic_trees):
    """
    Get branch information for logic tree without combinations across fault system logic trees.

    Parameters
    ----------
    logic_trees: list
        logic tree definition
    
    Returns
    -------
    lt_branches: List[dict]
        each dict contains 'source_ids' and 'nrlz' of logic tree branch
    """

    lt_branches = []
    for logic_tree in logic_trees: 
        # print(logic_tree)
        for ltb in get_granular_logic_tree_branches_wnrlz(logic_tree):
            # print(ltb)
            source_ids = [v for k,v in ltb.items() if '_id' in k]
            lt_branches.append({'source_ids': source_ids, 'nrlz': ltb['nrlz']})

    return lt_branches

def get_disagg_configs(gt_config, logic_trees):
    """
    Get a configuration used for launching oq-engine disaggregations for
    every branch of a logic tree without forming combinations between fault system logic trees.

    Parameters
    ----------
    gt_config : dict
        contains information about location, vs30, poe, etc for disaggregation
        {
        'location':str, (could be site_code or encoded lat~lon)
        'poe':float (0-1),
        'vs30':float,
        'imt': str,
        'inv_time': float,
        'agg': str,
        'hazard_model_id': str
        }
    logic_trees : list
        logic tree definition

    Returns
    -------
    list
        Format matches output from THP --deagg CONFIG but does not contain 'source_tree_hazid' key
    """

    configs = gt_config.copy()
    LOCATIONS_BY_ID.update(LOCATIONS_SRWG214_BY_ID)
    if LOCATIONS_BY_ID.get(configs['location']):
        configs['site_code'] = configs['location']
        configs['site_name'] = LOCATIONS_BY_ID[configs['location']]['name']
        resolution = 0.001
        lat = LOCATIONS_BY_ID[configs['location']]['latitude']
        lon = LOCATIONS_BY_ID[configs['location']]['longitude']
        location = CodedLocation(lat, lon, resolution).code
        configs['location'] = location
    elif '~' in configs['location']:
        location = configs['location']
    else:
        raise Exception('location must be valid site_code or coded location')

    configs['target_level'] = get_target_level(gt_config, location)
    configs['deagg_specs'] = get_lt_branches(logic_trees)

    return [configs]


def build_task(task_arguments, job_arguments, task_id, extra_env):

    if CLUSTER_MODE == EnvMode['AWS']:
        job_name = f"Runzi-automation-oq-disagg-{task_id}"
        config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

        return get_ecs_job_config(job_name,
            'N/A', config_data,
            toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
            task_module=runzi.execute.openquake.oq_hazard_task.__name__,
            time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4,
            job_definition="Fargate-runzi-openquake-JD",
            # job_definition="SydneyRunziOpenquakeJD",
            # job_queue = "SydneyManagedFargateJQ",
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


def build_hazard_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, hazard_config: str, disagg_configs: Iterable):
    task_count = 0
    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]


    for disagg_config in disagg_configs: # 'source_ids', 'nrlz', 'hazard_solution_id'
        for disagg_specs in disagg_config['deagg_specs']:
            
            task_count +=1

            full_config = disagg_specs.copy()
            full_config['location'] = disagg_config['location']
            full_config['site_name'] = disagg_config.get('site_name')
            full_config['site_code'] = disagg_config.get('site_code')
            full_config['vs30'] = disagg_config['vs30']
            full_config['imt'] = disagg_config['imt']
            full_config['poe'] = disagg_config['poe']
            full_config['inv_time'] = disagg_config['inv_time']
            full_config['target_level'] = disagg_config['target_level']
            full_config['level'] = disagg_config['target_level'] # this is the level at which we calculate the disagg
            full_config['disagg_settings'] = disagg_config['disagg_settings']
            

            task_arguments = dict(
                hazard_config = hazard_config, #  upstream modified config File archive object
                #upstream_general_task=source_gt_id,
                model_type = model_type.name,
                disagg_config = full_config,
                )

            # print('')
            # print('task arguments MERGED')
            # print('==========================')
            # print(task_arguments)
            # print('==========================')
            # print('')

            job_arguments = dict(
                task_id = task_count,
                general_task_id = general_task_id,
                use_api = USE_API,
            )

            yield build_task(task_arguments, job_arguments, task_count, extra_env)