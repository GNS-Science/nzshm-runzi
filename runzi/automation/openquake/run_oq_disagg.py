# noqa: WIP
"""
This script produces disagg tasks in either AWS, PBS or LOCAL that run OpenquakeHazard in disagg mode.

"""
import json
import logging
from collections import namedtuple
from typing import Any, Dict

from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType

# from .run_oq_hazard import update_location_list, validate_config, get_model, get_num_workers, single_to_list
from runzi.configuration.openquake.oq_disagg import build_disagg_tasks

from .config import DisaggConfig

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


def build_tasks(job_config: DisaggConfig, task_type: SubtaskType, model_type: ModelType):

    scripts = []
    gt_ids = []
    for script_file, gt_id in build_disagg_tasks(task_type, model_type, job_config):
        scripts.append(script_file)
        if gt_id not in gt_ids:
            gt_ids.append(gt_id)

    return scripts, gt_ids


def run_oq_disagg(config: Dict[str, Any]) -> None:

    task_type = SubtaskType.OPENQUAKE_HAZARD
    model_type = ModelType.COMPOSITE
    job_config = DisaggConfig.model_validate(config)

    # some objects in the config (Path type) are not json serializable so we dump to json using the pydantic method
    # which handles these types and load back to json to clean it up so it can be passed to the toshi API
    # args_dict = json.loads(job_config.model_dump_json())

    num_workers = job_config.calculation.num_workers

    # location_list = update_location_list(config["site_params"]["locations"])  # noqa: F821
    # vs30s = single_to_list(config["site_params"]["vs30"])  # noqa: F821
    # aggs = single_to_list(config["hazard_curve"]["agg"])  # noqa: F821
    # location_codes, junk = get_coded_locations(location_list)  # noqa: F821

    # args = dict(
    #     general=config["general"],
    #     hazard_model_id=config["hazard_curve"]["hazard_model_id"],
    #     srm_logic_tree=srm_logic_tree,
    #     gmcm_logic_tree=gmcm_logic_tree,
    #     imts=config["hazard_curve"]["imts"],
    #     aggs=aggs,
    #     vs30s=vs30s,
    #     poes=config["disagg"]["poes"],
    #     inv_time=config["disagg"]["inv_time"],
    #     location_codes=location_codes,
    #     config_iterate=openquake_iterate,
    #     config_scalar=openquake_scalar,
    #     sleep_multiplier=config["calculation"].get("sleep_multiplier"),
    # )

    # we don't create a new GT (if using the API) here because there is a GT created for each disaggregation
    # (which will spawn as many tasks as there are branches in the SRM LT). This is done because the GT is used
    # to track the particular disaggrgation configuration for later lookup by THP. THSv4 should remove this
    # necessity as we can lookup relizations without the need to refer to a hazard solution ID.
    tasks, gt_ids = build_tasks(job_config, task_type, model_type)
    print('worker count: ', num_workers)
    print(f'tasks to schedule: {len(tasks)}')
    print(gt_ids)
    schedule_tasks(tasks, num_workers)

    with open(config["output"]["gt_filename"], 'w', buffering=1) as gtfile:
        gtfile.write('\n'.join(gt_ids))

    print("_____________________GT IDs______________________")
    for _id in gt_ids:
        print(_id)
