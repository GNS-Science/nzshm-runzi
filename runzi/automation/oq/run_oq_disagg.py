#!python3
"""
This script produces disagg tasks in either AWS, PBS or LOCAL that run OpenquakeHazard in disagg mode.

"""
import logging
from collections import namedtuple
from typing import Dict, Any

from .run_oq_hazard import update_location_list, validate_config, load_model, get_num_workers, single_to_list
from runzi.configuration.oq.oq_disagg import build_disagg_tasks
from runzi.execute.openquake.util.oq_build_sites import get_coded_locations
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType
from runzi.automation.scaling.schedule_tasks import schedule_tasks

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


def build_tasks(args, task_type, model_type):

    scripts = []
    gt_ids = []
    for script_file, gt_id in build_disagg_tasks(task_type, model_type, args):
        scripts.append(script_file)
        if gt_id not in gt_ids:
            gt_ids.append(gt_id)

    return scripts, gt_ids


def run_oq_disagg_f(config: Dict[Any, Any]) -> None:

    task_type = SubtaskType.OPENQUAKE_HAZARD
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
        general=config["general"],
        hazard_model_id=config["hazard_curve"]["hazard_model_id"],
        srm_logic_tree=srm_logic_tree,
        gmcm_logic_tree=gmcm_logic_tree,
        imts=config["hazard_curve"]["imts"],
        aggs=aggs,
        vs30s=vs30s,
        poes=config["disagg"]["poes"],
        inv_time=config["disagg"]["inv_time"],
        location_codes=location_codes,
        config_iterate=openquake_iterate,
        config_scalar=openquake_scalar,
    )

    # we don't create a new GT (if using the API) here because there is a GT created for each disaggregation
    # (which will spawn as many tasks as there are branches in the SRM LT). This is done because the GT is used
    # to track the particular disaggrgation configuration for later lookup by THP. THSv2.0 should remove this
    # necessity as we can lookup relizations without the need to refer to a hazard solution ID.
    tasks, gt_ids = build_tasks(args, task_type, model_type)
    print('worker count: ', num_workers)
    print(f'tasks to schedule: {len(tasks)}')
    print(gt_ids)
    schedule_tasks(tasks, num_workers)

    with open(config["output"]["gt_filename"], 'w', buffering=1) as gtfile:
        gtfile.write('\n'.join(*gt_ids))

    print("_____________________GT IDs______________________")
    for _id in gt_ids:
        print(_id)
