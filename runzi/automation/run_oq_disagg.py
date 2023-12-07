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

from runzi.automation.run_oq_hazard import update_location_list
from runzi.automation.config import validate_entry, validate_path, load_logic_tree
from runzi.execute.openquake.util.oq_build_sites import get_coded_locations
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_disagg import build_hazard_tasks, get_disagg_configs
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (USE_API, 
    API_KEY, API_URL)


Disagg = namedtuple("Disagg", "location imt vs30 poe")

def launch_gt(gt_config, logic_tree, num_workers):

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    # logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    # logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    # logging.getLogger('urllib3').setLevel(loglevel)
    # logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('gql.transport').setLevel(logging.WARN)
    log = logging.getLogger(__name__)

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Disagg calcs"
    TASK_DESCRIPTION = f"hazard ID: {gt_config['hazard_model_id']}, hazard aggregation target: {gt_config['agg']}"

    # disagg_settings = dict(mag_bin_width = 0.499)
    # disagg_settings = dict(mag_bin_width = 0.5)
    disagg_settings = dict(
        disagg_bin_edges = {'dist': [0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 140.0, 180.0, 220.0, 260.0, 320.0, 380.0, 500.0]},
        num_epsilon_bins = 16,
        mag_bin_width = .1999,
        coordinate_bin_width = 5,
        disagg_outputs = "TRT Mag Dist Mag_Dist TRT_Mag_Dist_Eps"
        # disagg_outputs = "TRT Mag Dist Mag_Dist Mag_Dist_TRT_Eps"
    )

    disagg_configs = get_disagg_configs(gt_config, logic_tree)
    for disagg_config in disagg_configs:
        disagg_config['disagg_settings'] = disagg_settings

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    # TODO obtain the config (job.ini from the first nearest_rlz)
    hazard_config = "RmlsZToyODQ4OTc1" # GSIM LT v2, no sites, renew 2023-04-29
            

    args = dict(
        hazard_config = hazard_config,
        disagg_configs =  disagg_configs,
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD #TODO: create a new task type
    model_type = ModelType.COMPOSITE

    if USE_API:

        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(task_type)\
            .set_model_type(model_type)

        new_gt_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", new_gt_id)

    #tasks = build_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs)

    tasks = list(build_hazard_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs))
    if USE_API:
        toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))

    print(tasks)
    print('worker count: ', num_workers)
    print(f'tasks to schedule: {len(tasks)}')
    schedule_tasks(tasks, num_workers)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return new_gt_id


def generate_gt_configs(task_args, locations, poes, vs30s, imts):

    for (loc, poe, vs30, imt) in itertools.product(locations, poes, vs30s, imts):
        yield dict(task_args,
            location = loc,
            poe = poe,
            vs30 = vs30,
            imt = imt,
        )


def start_disagg_jobs(task_args, locations, imts, vs30s, poes, gt_filename, logic_tree, num_workers):

    gt_ids = []
    with open(gt_filename, 'w', buffering=1) as gtfile:
        for gt_config in generate_gt_configs(task_args, locations, poes, vs30s, imts): 
            gt_id = launch_gt(gt_config, logic_tree, num_workers)
            gt_ids.append(gt_id)
            gtfile.write(gt_id + '\n')
    return gt_ids

def validate_config(config: Dict[Any, Any]) -> None:
    validate_path(config, "logic_tree")
    validate_entry(config, "hazard_model_id", str)
    validate_entry(config, "agg", str)
    validate_entry(config, "inv_time", int)
    validate_entry(config, "rupture_mesh_spacing", int)
    validate_entry(config, "ps_grid_spacing", int)
    validate_entry(config, "locations", list, elm_type=str)
    validate_entry(config, "imts", list, elm_type=str)
    validate_entry(config, "vs30s", list, elm_type=int)
    validate_entry(config, "poes", list, elm_type=float)
    validate_entry(config, "gt_filename", str)
    validate_entry(config, "num_workers", int, optional=True)

def run_oq_disagg_f(config: Dict[Any, Any]) -> None:

    validate_config(config)
    logic_tree = load_logic_tree(config["logic_tree"])
    if not config.get("num_workers"):
        config["num_workers"] = 1
    location_list = update_location_list(config["locations"])
    print(location_list)

    task_args = dict(
        hazard_model_id = config["hazard_model_id"],
        agg = config["agg"],
        inv_time = config["inv_time"],
        rupture_mesh_spacing = config["rupture_mesh_spacing"],
        ps_grid_spacing = config["ps_grid_spacing"], #km 
    )

    location_codes, junk = get_coded_locations(location_list)

    gt_ids = start_disagg_jobs(
        task_args,
        location_codes,
        config["imts"],
        config["vs30s"],
        config["poes"],
        config["gt_filename"],
        logic_tree,
        config["num_workers"],
    )

    print("_____________________GT IDs______________________")
    for id in gt_ids:
        print(id)