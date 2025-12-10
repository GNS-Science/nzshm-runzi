# this is a temporary fix to convert args of list type to single values
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from pydantic import BaseModel


def generate_automation_task_args(task_args: 'BaseModel') -> dict[str, Any]:
    automation_task_args = task_args.model_dump(mode='json')
    for k in automation_task_args.keys():
        automation_task_args[k] = automation_task_args[k][0]
    return automation_task_args
