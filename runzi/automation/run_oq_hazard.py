#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that run OpenquakeHazard

"""
import csv
import logging
import pwd
import os
import datetime as dt
from pathlib import Path
from collections import namedtuple
from typing import Any, Dict, List

from nzshm_common.location.code_location import CodedLocation
from nzshm_model.source_logic_tree.slt_config import from_config

from runzi.automation.config import validate_entry, load_logic_tree, validate_path
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_hazard import build_hazard_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import USE_API, API_KEY, API_URL


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


def validate_config(config: Dict[Any, Any]) -> None:
    validate_path(config, "logic_tree", "srm_logic_tree")
    validate_entry(config, "hazard_curve", "imts", [list], elm_type=str)
    validate_entry(config, "hazard_curve", "imtls", [list], elm_type=float)
    validate_entry(config, "site_params", "vs30", [list, int], elm_type=int)
    validate_entry(config, "site_params", "location_list", [list], elm_type=str)
    validate_entry(config, "general", "title", [str])
    validate_entry(config, "general", "description", [str])
    validate_entry(config, "logic_tree", "slt_decomposition", [str], choice=["none", "composite", "component"])
    validate_entry(config, "calculation", "num_workers", [int], optional=True)


def update_location_list(location_list: List[str]):

    location_list_new = []
    for location in location_list:
        if Path(location).exists():
            location_list_new += locations_from_csv(location)
        else:
            location_list_new.append(location)

    return location_list_new

def run_oq_hazard_f(config: Dict[Any, Any]):

    validate_config(config)
    if config["logic_tree"]["slt_decomposition"] in ["composite", "none"]:
        msg = (f"config['logic_tree']['slt_decomposition'] SRM logic tree not supported. "
               "See https://github.com/GNS-Science/nzshm-model/issues/23 and "
               "https://github.com/GNS-Science/nzshm-runzi/issues/162")
        raise ValueError(msg)

    srm_logic_tree = from_config(config["logic_tree"]["srm_logic_tree"])
    with Path(config["calculation"]["gsim_logic_tree_file"]).open() as gltf:
        gmcm_logic_tree = gltf.read()

    if not config["calculation"].get("num_workers"):
        config["calculation"]["num_workers"] = 1

    location_list = update_location_list(config["site_params"]["location_list"])

    imts = config["hazard_curve"]["imts"]
    imtls = config["hazard_curve"]["imtls"]

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

    openquake_iterate = dict() if not config.get("openquake_iterate") else config["openquake_iterate"]
    openquake_scalar = dict() if not config.get("openquake_single") else config["openquake_single"]
    args = dict(
        general = config["general"],
        srm_logic_tree =  srm_logic_tree,
        gmcm_logic_tree = gmcm_logic_tree,
        slt_decomposition = config["logic_tree"]["slt_decomposition"],
        intensity_spec = { "tag": "fixed", "measures": imts, "levels": imtls},
        vs30 = config["site_params"]["vs30"],
        location_list = location_list,
        disagg_conf = {'enabled': False, 'config': {}},
        config_iterate = openquake_iterate,
        config_scalar = openquake_scalar,
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
    
    print('worker count: ', config["calculation"]["num_workers"])
    print(f'tasks to schedule: {len(tasks)}')
    schedule_tasks(tasks, config["calculation"]["num_workers"])

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
