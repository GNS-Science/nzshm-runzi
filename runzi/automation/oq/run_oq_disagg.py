#!python3
"""
This script produces disagg tasks in either AWS, PBS or LOCAL that run OpenquakeHazard in disagg mode.

"""
import argparse
import logging
import csv
import json
import pwd
import os
import itertools
from collections import namedtuple
import datetime as dt
from pathlib import Path
from typing import Dict, Any

from nzshm_common.location.location import location_by_id, LOCATION_LISTS
from nzshm_common.grids import load_grid
from nzshm_common.location.code_location import CodedLocation

from .run_oq_hazard import update_location_list, validate_config, load_model, get_num_workers, single_to_list
from runzi.configuration.oq.oq_disagg import build_disagg_tasks
from runzi.execute.openquake.util.oq_build_sites import get_coded_locations
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (USE_API, 
    API_KEY, API_URL)

loglevel = logging.INFO
logging.basicConfig(level=logging.INFO)
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('botocore').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)
logging.getLogger('gql.transport').setLevel(logging.WARN)


log = logging.getLogger(__name__)


Disagg = namedtuple("Disagg", "location imt vs30 poe")

# def launch_gt(gt_config, logic_tree, num_workers):

#     t0 = dt.datetime.utcnow()

#     new_gt_id = None

#     # If using API give this task a descriptive setting...

#     TASK_TITLE = "Openquake Disagg calcs"
#     TASK_DESCRIPTION = f"hazard ID: {gt_config['hazard_model_id']}, hazard aggregation target: {gt_config['agg']}"

#     # disagg_settings = dict(mag_bin_width = 0.499)
#     # disagg_settings = dict(mag_bin_width = 0.5)
#     disagg_settings = dict(
#         disagg_bin_edges = {'dist': [0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 140.0, 180.0, 220.0, 260.0, 320.0, 380.0, 500.0]},
#         num_epsilon_bins = 16,
#         mag_bin_width = .1999,
#         coordinate_bin_width = 5,
#         disagg_outputs = "TRT Mag Dist Mag_Dist TRT_Mag_Dist_Eps"
#         # disagg_outputs = "TRT Mag Dist Mag_Dist Mag_Dist_TRT_Eps"
#     )

#     disagg_configs = get_disagg_configs(gt_config, logic_tree)
#     for disagg_config in disagg_configs:
#         disagg_config['disagg_settings'] = disagg_settings

#     headers={"x-api-key":API_KEY}
#     toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

#     # TODO obtain the config (job.ini from the first nearest_rlz)
#     hazard_config = "RmlsZToyODQ4OTc1" # GSIM LT v2, no sites, renew 2023-04-29
            

#     args = dict(
#         hazard_config = hazard_config,
#         disagg_configs =  disagg_configs,
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
#             .set_subtask_type(task_type)\
#             .set_model_type(model_type)

#         new_gt_id = toshi_api.general_task.create_task(gt_args)

#     print("GENERAL_TASK_ID:", new_gt_id)

#     #tasks = build_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs)

#     tasks = list(build_hazard_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs))
#     if USE_API:
#         toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))

#     print(tasks)
#     print('worker count: ', num_workers)
#     print(f'tasks to schedule: {len(tasks)}')
#     schedule_tasks(tasks, num_workers)

#     print("GENERAL_TASK_ID:", new_gt_id)
#     print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

#     return new_gt_id


# def generate_gt_configs(task_args, locations, poes, vs30s, imts):

#     for (loc, poe, vs30, imt) in itertools.product(locations, poes, vs30s, imts):
#         yield dict(task_args,
#             location = loc,
#             poe = poe,
#             vs30 = vs30,
#             imt = imt,
#         )


# def start_disagg_jobs(task_args, locations, imts, vs30s, poes, gt_filename, logic_tree, num_workers):

#     gt_ids = []
#     with open(gt_filename, 'w', buffering=1) as gtfile:
#         for gt_config in generate_gt_configs(task_args, locations, poes, vs30s, imts): 
#             gt_id = launch_gt(gt_config, logic_tree, num_workers)
#             gt_ids.append(gt_id)
#             gtfile.write(gt_id + '\n')
#     return gt_ids


def build_tasks(args, task_type, model_type):

    scripts = []
    gt_ids = []
    for script_file, gt_id in build_disagg_tasks(task_type, model_type, args):
        scripts.append(script_file)
        if not gt_id in gt_ids:
            gt_ids.append(gt_id)

    return scripts, gt_ids


def run_oq_disagg_f(config: Dict[Any, Any]) -> None:
    
    task_type = SubtaskType.OPENQUAKE_HAZARD #TODO: create a new task type
    model_type = ModelType.COMPOSITE

    validate_config(config, mode='disagg')
    srm_logic_tree, gmcm_logic_tree = load_model(config)
    num_workers = get_num_workers(config)
    location_list = update_location_list(config["site_params"]["locations"])
    vs30s = single_to_list(config["site_params"]["vs30"])
    aggs = single_to_list(config["hazard_curve"]["agg"])
    location_codes, junk = get_coded_locations(location_list)

    openquake_iterate = dict() if not config.get("openquake_iterate") else config["openquake_iterate"]
    openquake_scalar = dict() if not config.get("openquake_single") else config["openquake_single"]
    args = dict(
        general = config["general"],
        hazard_model_id = config["hazard_curve"]["hazard_model_id"],
        srm_logic_tree =  srm_logic_tree,
        gmcm_logic_tree = gmcm_logic_tree,
        imts = config["hazard_curve"]["imts"],
        aggs = aggs,
        vs30s = vs30s,
        poes = config["disagg"]["poes"],
        inv_time = config["disagg"]["inv_time"],
        location_codes = location_codes,
        config_iterate = openquake_iterate,
        config_scalar = openquake_scalar,
    )

    # we don't create a new GT (if using the API) here because there is a GT created for each disaggregation
    # (which will spawn as many tasks as there are branches in the SRM LT). This is done because the GT is used
    # to track the particular disaggrgation configuration for later lookup by THP. THSv2.0 should remove this
    # necessity as we can lookup relizations without the need to refer to a hazard solution ID.
    tasks, gt_ids = build_tasks(args, task_type, model_type)
    print('worker count: ', num_workers)
    print(f'tasks to schedule: {len(tasks)}')
    print(gt_ids)
    assert 0
    schedule_tasks(tasks, num_workers)

    with open(config["output"]["gt_filename"], 'w', buffering=1) as gtfile:
        gtfile.write('\n'.join(*gt_ids))

    print("_____________________GT IDs______________________")
    for _id in gt_ids:
        print(_id)