#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that run OpenquakeHazard

"""
import datetime as dt
import getpass
import json
import logging
from typing import Any, Dict

from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, S3_URL, USE_API, EnvMode
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.configuration.openquake.oq_hazard import build_hazard_tasks

from .hazard_inputs import HazardInput

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


def build_tasks(new_gt_id: str, args: Dict[str, Any], task_type: SubtaskType, model_type: ModelType):
    scripts = []
    for script_file in build_hazard_tasks(new_gt_id, task_type, model_type, args):
        print("scheduling: ", script_file)
        scripts.append(script_file)

    return scripts


def run_oq_hazard(job_input: HazardInput) -> str | None:

    # cluster mode cannot be AWS if API is disabled
    if CLUSTER_MODE is EnvMode.AWS and not USE_API:
        raise Exception("Toshi API must be enabled when cluster mode is AWS")

    t0 = dt.datetime.now(dt.timezone.utc)

    # some objects in the config (Path type) are not json serializable so we dump to json using the pydantic method
    # which handles these types and load back to json to clean it up so it can be passed to the toshi API
    args_dict = json.loads(job_input.model_dump_json())

    num_workers = job_input.calculation.num_workers

    task_type = SubtaskType.OPENQUAKE_HAZARD
    model_type = ModelType.COMPOSITE
    if USE_API:
        headers = {"x-api-key": API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        # upload files
        file_paths = [
            (job_input.site_params.locations_file, "site_params", "locations_file_id"),
            (job_input.hazard_model.gmcm_logic_tree, "hazard_model", "gmcm_logic_tree_id"),
            (job_input.hazard_model.srm_logic_tree, "hazard_model", "srm_logic_tree_id"),
            (job_input.hazard_model.hazard_config, "hazard_model", "hazard_config_id"),
        ]
        for file_path, group, property in file_paths:
            if file_path:
                file_id, post_url = toshi_api.file.create_file(file_path)
                toshi_api.file.upload_content(post_url, file_path)
                args_dict[group][property] = file_id

        # create new task in toshi_api
        args_list = []
        for key, value in args_dict.items():
            val = value
            if not isinstance(val, str):
                val = json.dumps(val)
            args_list.append(dict(k=key, v=val))

        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=getpass.getuser(),
                title=job_input.general.title,
                description=job_input.general.description,
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

    return new_gt_id
