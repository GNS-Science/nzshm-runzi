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
from dataclasses import asdict

from nzshm_common.location import CodedLocation
from nzshm_model.logic_tree import SourceLogicTree, GMCMLogicTree
from nzshm_model import get_model_version, NshmModel
from nshm_toshi_client import ToshiFile

from runzi.automation.config import validate_entry, validate_path
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.openquake.oq_hazard import build_hazard_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import USE_API, API_KEY, API_URL, CLUSTER_MODE, EnvMode

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


def validate_config_hazard(config: Dict[Any, Any]) -> None:
    validate_entry(config, "hazard_curve", "imtls", [list], subtype=float)


def validate_config_disagg(config: Dict[Any, Any]) -> None:
    validate_entry(config, "hazard_curve", "hazard_model_id", [str])
    validate_entry(config, "disagg", "inv_time", [int])
    validate_entry(config, "disagg", "poes", [list], subtype=float)
    validate_entry(config, "output", "gt_filename", [str])
    validate_entry(config, "hazard_curve", "agg", [list, str], subtype=str)


def validate_config(config: Dict[Any, Any], mode: str) -> None:

    if config["site_params"].get("locations") and config["site_params"].get("locations_file"):
        raise ValueError("cannot specify both locations and locations_file in site_params table of config")

    has_srm_lt = has_gmcm_lt = has_hazard_config = False
    if config["model"].get("srm_logic_tree"):
        validate_path(config, "model", "srm_logic_tree")
        has_srm_lt = True
    if config["model"].get("gmcm_logic_tree"):
        validate_path(config, "model", "gmcm_logic_tree")
        has_gmcm_lt = True
    if config["model"].get("hazard_config"):
        validate_path(config, "model", "hazard_config")
        has_hazard_config = True
    
    if (
        not config["model"].get("nshm_model_version") and
        not (has_srm_lt and has_gmcm_lt and has_hazard_config)
    ):
        raise ValueError(
            """if nshm_model_version not specified, must provide all of
            gmcm_logic_tree, srm_logic_tree, and hazard_config file paths"""
        )

    file_has_vs30 = False
    if config["site_params"].get("locations"):
        validate_entry(config, "site_params", "locations", [list], subtype=str)
    else:
        validate_path(config, "site_params", "locations_file")
        with Path(config["site_params"]["locations_file"]).open() as lf:
            header = lf.readline()
            if "vs30" in header:
                file_has_vs30 = True

    validate_entry(config, "hazard_curve", "imts", [list], subtype=str)
    validate_entry(config, "general", "title", [str])
    validate_entry(config, "general", "description", [str])
    validate_entry(config, "calculation", "num_workers", [int], optional=True)
    validate_entry(config, "calculation", "sleep_multiplier", [float], optional=True)

    # config must either have a vs30 to apply to all sites (uniform site parameter) or
    # the locations file must have site-specific vs30s
    if config["site_params"].get("vs30"):
        if file_has_vs30:
            raise ValueError("cannot specify both uniform and site-specific vs30")
        validate_entry(config, "site_params", "vs30", [list, int], subtype=int)
    elif not file_has_vs30:
        raise ValueError("locations file must have vs30 column if uniform vs30 not given")

    if mode == 'hazard':
        validate_config_hazard(config)
    elif mode == 'disagg':
        validate_config_disagg(config)


def update_location_list(location_list: List[str]):

    location_list_new = []
    for location in location_list:
        if Path(location).exists():
            location_list_new += locations_from_csv(location)
        else:
            location_list_new.append(location)

    return location_list_new


def load_gmcm_str(gmcm_logic_tree_path):
    """temporoary until we can serialize a gmcm logic tree object"""
    with Path(gmcm_logic_tree_path).open() as gltf:
        return gltf.read()


def get_model(config) -> NshmModel:
    """retrive the model specification from the config. User can specifiy a model version availble
    in `nzshm-model` and/or files for model components (logic trees and hazard configuration). If
    both are given, files will override what is loaded from the model version."""
    pass

    if config["model"].get("nshm_model_version"):
        model = get_model_version(config["model"]["nshm_model_version"])
    # if config
        raise NotImplementedError("cannot specify model as seperate parts")
        srm_logic_tree = SourceLogicTree.from_json(config["model"]["srm_logic_tree"])
        gmcm_logic_tree = GMCMLogicTree.from_json(config["model"]["gmcm_logic_tree"])

    return model


def get_num_workers(config: Dict[Any, Any]) -> int:
    if not config["calculation"].get("num_workers"):
        return 1
    return config["calculation"]["num_workers"]


def single_to_list(param: Any) -> List[Any]:
    return param if isinstance(param, list) else [param]


def build_tasks(new_gt_id, args, task_type, model_type):

    scripts = []
    for script_file in build_hazard_tasks(new_gt_id, task_type, model_type, args):
        print('scheduling: ', script_file)
        scripts.append(script_file)

    return scripts


def run_oq_hazard(config: Dict[Any, Any]):

    t0 = dt.datetime.now(dt.timezone.utc)

    validate_config(config, mode='hazard')
    args = config

    # if using a locations file and cloud compute, save the file using ToshiAPI for later retrieval by each task
    if config["site_params"].get("locations_file") and CLUSTER_MODE is EnvMode['AWS']:
        headers = {"x-api-key": API_KEY}
        file_api = ToshiFile(API_URL, None, None, with_schema_validation=True, headers=headers) 
        args["site_params"]["locations_file_id"], _ = file_api.create_file(config["site_params"]["locations_file"])

    num_workers = get_num_workers(config)

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD
    model_type = ModelType.COMPOSITE

    if USE_API:
        headers = {"x-api-key": API_KEY}
        toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)
        # create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=config["general"]["title"],
            description=config["general"]["description"]
        )\
            .set_argument_list(args_list)\
            .set_subtask_type(task_type)\
            .set_model_type(model_type)
        new_gt_id = toshi_api.general_task.create_task(gt_args)
    else:
        new_gt_id = None

    print("GENERAL_TASK_ID:", new_gt_id)
    tasks = build_tasks(new_gt_id, args, task_type, model_type)

    print('worker count: ', num_workers)
    print(f'tasks to schedule: {len(tasks)}')
    schedule_tasks(tasks, num_workers)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.now(dt.timezone.utc) - t0).total_seconds())
