import base64

from runzi.arguments import ArgSweeper
from runzi.automation.file_utils import get_output_file_ids
from runzi.automation.local_config import API_URL, get_auth_kwargs
from runzi.automation.toshi_api import ToshiApi


def get_toshi_api() -> ToshiApi:
    return ToshiApi(API_URL, None, None, with_schema_validation=True, **get_auth_kwargs())


def get_solution_ids_from_id(toshi_id):
    """Convert a general task ID to a list of inversion solutions produced by that GT.

    If the input id is not a GeneralTask, return the input id as a single element list.

    Args:
        toshi_id: The input ID, either a solution inversion or general task.

    Returns:
        A list of solutution ids."""
    if 'GeneralTask' in str(base64.b64decode(toshi_id)):
        return [out['id'] for out in get_output_file_ids(get_toshi_api(), toshi_id)]

    return [toshi_id]


def convert_gt_to_swept(argument_sweeper: ArgSweeper):
    solution_ids = []
    for task_args in argument_sweeper.get_tasks():
        solution_ids += get_solution_ids_from_id(task_args.source_solution_id)  # type: ignore
    argument_sweeper.swept_args['source_solution_id'] = solution_ids
