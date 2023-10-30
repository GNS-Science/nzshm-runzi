#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that run OpenquakeHazard

"""
import csv
import logging
import pwd
import os
import datetime as dt
from dateutil.tz import tzutc
from pathlib import Path
from collections import namedtuple
from typing import Any, Dict

from nzshm_common.location.code_location import CodedLocation

from runzi.automation.config import validate_entry, load_logic_tree, validate_path
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_hazard import build_hazard_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )


def locations_from_csv(locations_filepath):

    locations = []
    locations_filepath = Path(locations_filepath)
    with locations_filepath.open('r') as locations_file:
        reader = csv.reader(locations_file)
        Location = namedtuple("Location", next(reader), rename=True)
        for row in reader:
            location = Location(*row)
            locations.append(
                CodedLocation(lat=float(location.lat), lon=float(location.lon), resolution=0.001).code
            )
    return locations


def build_tasks(new_gt_id, args, task_type, model_type):

    scripts = []
    for script_file in build_hazard_tasks(new_gt_id, task_type, model_type, args):
        print('scheduling: ', script_file)
        scripts.append(script_file)

    return scripts


def validate_config(config):
    validate_path(config, "logic_tree")
    validate_entry(config, "imts", list, elm_type=str)
    validate_entry(config, "imtls", list, elm_type=float)
    validate_entry(config, "vs30s", list, elm_type=int)
    validate_entry(config, "location_lists", list, elm_type=list)
    validate_entry(config, "rupture_mesh_spacings", list, elm_type=int)
    validate_entry(config, "ps_grid_spacings", list, elm_type=int)
    validate_entry(config, "config_archive_ids", list, elm_type=str)
    validate_entry(config, "title", str)
    validate_entry(config, "description", str)
    validate_entry(config, "num_workers", int, optional=True)
    

def run_oq_hazard_f(config: Dict[Any, Any]):

    validate_config(config)
    logic_tree = load_logic_tree(config["logic_tree"])
    if not config.get("num_workers"):
        config["num_workers"] = 1

    t0 = dt.datetime.utcnow()

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

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    args = dict(
        # a Toshi File containing zipped configuration
        config_archive_ids = config["config_archive_ids"],
        logic_tree_permutations =  logic_tree.logic_tree_permutations,
        intensity_specs = [
            { "tag": "fixed", "measures": config["imts"], "levels": config["imtls"]},
        ],
        vs30s = config["vs30s"],
        location_lists = config["location_lists"],
        disagg_confs = [{'enabled': False, 'config': {}},
        ],
        rupture_mesh_spacings = config["rupture_mesh_spacings"],
        ps_grid_spacings = config["ps_grid_spacings"],  # km
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD
    model_type = ModelType.COMPOSITE

    if USE_API:

        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=config["title"],
            description=config["description"]
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(task_type)\
            .set_model_type(model_type)

        new_gt_id = toshi_api.general_task.create_task(gt_args)
    else:
        new_gt_id = None

    print("GENERAL_TASK_ID:", new_gt_id)

    tasks = build_tasks(new_gt_id, args, task_type, model_type)
    
    print('worker count: ', config["num_workers"])
    print(f'tasks to schedule: {len(tasks)}')
    schedule_tasks(tasks, config["num_workers"])

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
