# noqa: WIP
"""
This script produces disagg tasks in either AWS, PBS or LOCAL that run OpenquakeHazard in disagg mode.

"""
import logging
from collections import namedtuple

from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.configuration.openquake.oq_disagg import build_disagg_tasks

from .hazard_inputs import DisaggInput

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


def build_tasks(job_config: DisaggInput, task_type: SubtaskType, model_type: ModelType):

    scripts = []
    gt_ids = []
    for script_file, gt_id in build_disagg_tasks(task_type, model_type, job_config):
        scripts.append(script_file)
        if gt_id not in gt_ids:
            gt_ids.append(gt_id)

    return scripts, gt_ids


def run_oq_disagg(job_input: DisaggInput) -> list[str]:

    task_type = SubtaskType.OPENQUAKE_HAZARD
    model_type = ModelType.COMPOSITE

    num_workers = job_input.calculation.num_workers

    # we don't create a new GT (if using the API) here because there is a GT created for each disaggregation
    # (which will spawn as many tasks as there are branches in the SRM LT). This is done because the GT is used
    # to track the particular disaggrgation configuration for later lookup by THP. THSv4 should remove this
    # necessity as we can lookup relizations without the need to refer to a hazard solution ID.
    tasks, gt_ids = build_tasks(job_input, task_type, model_type)
    print('worker count: ', num_workers)
    print(f'tasks to schedule: {len(tasks)}')
    print(gt_ids)
    schedule_tasks(tasks, num_workers)

    with open(job_input.output.gt_filename, 'w', buffering=1) as gtfile:
        gtfile.write('\n'.join(gt_ids))

    print("_____________________GT IDs______________________")
    for _id in gt_ids:
        print(_id)

    return gt_ids
