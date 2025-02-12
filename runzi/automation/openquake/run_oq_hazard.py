#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that run OpenquakeHazard

"""
import datetime as dt
import json
import logging
import os
import pwd
from pathlib import Path
from typing import Any, Dict, List

from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, S3_URL, USE_API, EnvMode
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.configuration.openquake.oq_hazard import build_hazard_tasks

from .config import HazardConfig

loglevel = logging.INFO
logging.basicConfig(level=logging.INFO)
logging.getLogger("py4j.java_gateway").setLevel(loglevel)
logging.getLogger("nshm_toshi_client.toshi_client_base").setLevel(loglevel)
logging.getLogger("nshm_toshi_client.toshi_file").setLevel(loglevel)
logging.getLogger("urllib3").setLevel(loglevel)
logging.getLogger("botocore").setLevel(loglevel)
logging.getLogger("git.cmd").setLevel(loglevel)
logging.getLogger("gql.transport").setLevel(logging.WARN)

log = logging.getLogger(__name__)


def validate_config_disagg(config: Dict[Any, Any]) -> None:
    pass
    # validate_entry(config, "hazard_curve", "hazard_model_id", [str])
    # validate_entry(config, "disagg", "inv_time", [int])
    # validate_entry(config, "disagg", "poes", [list], subtype=float)
    # validate_entry(config, "output", "gt_filename", [str])
    # validate_entry(config, "hazard_curve", "agg", [list, str], subtype=str)


def load_gmcm_str(gmcm_logic_tree_path):
    """temporoary until we can serialize a gmcm logic tree object"""
    with Path(gmcm_logic_tree_path).open() as gltf:
        return gltf.read()


def get_num_workers(config: Dict[str, Any]) -> int:
    if not config["calculation"].get("num_workers"):
        return 1
    return config["calculation"]["num_workers"]


def single_to_list(param: Any) -> List[Any]:
    return param if isinstance(param, list) else [param]


def build_tasks(new_gt_id: str, args: Dict[str, Any], task_type: SubtaskType, model_type: ModelType):
    scripts = []
    for script_file in build_hazard_tasks(new_gt_id, task_type, model_type, args):
        print("scheduling: ", script_file)
        scripts.append(script_file)

    return scripts


def run_oq_hazard(config: Dict[str, Any]):
    t0 = dt.datetime.now(dt.timezone.utc)

    hazard_job_config = HazardConfig.model_validate(config)

    # some objects in the config (Path type) are not json serializable so we dump to json and load
    # back to json to clean it up so it can be passed to the toshi API
    args_dict = json.loads(hazard_job_config.model_dump_json())

    # if using a locations file and cloud compute, save the file using ToshiAPI for later retrieval by each task
    toshi_api = None
    if hazard_job_config.site_params.locations_file and CLUSTER_MODE is EnvMode["AWS"]:
        filepath = hazard_job_config.site_params.locations_file
        headers = {"x-api-key": API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        file_id, post_url = toshi_api.file.create_file(filepath)
        toshi_api.file.upload_content(post_url, filepath)
        args_dict["site_params"]["locations_file_id"] = file_id
        print("site file ID", file_id)

    num_workers = get_num_workers(config)

    args_list = []
    for key, value in args_dict.items():
        val = value
        if not isinstance(val, str):
            val = json.dumps(val)
        args_list.append(dict(k=key, v=val))

    task_type = SubtaskType.OPENQUAKE_HAZARD
    model_type = ModelType.COMPOSITE

    if USE_API:
        if not toshi_api:
            headers = {"x-api-key": API_KEY}
            toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=pwd.getpwuid(os.getuid()).pw_name,
                title=config["general"]["title"],
                description=config["general"]["description"],
            )
            .set_argument_list(args_list)
            .set_subtask_type(task_type)
            .set_model_type(model_type)
        )
        new_gt_id = toshi_api.general_task.create_task(gt_args)
    else:
        new_gt_id = None

    print("GENERAL_TASK_ID:", new_gt_id)
    tasks = build_tasks(new_gt_id, args_dict, task_type, model_type)

    print("worker count: ", num_workers)
    print(f"tasks to schedule: {len(tasks)}")
    schedule_tasks(tasks, num_workers)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.now(dt.timezone.utc) - t0).total_seconds())
