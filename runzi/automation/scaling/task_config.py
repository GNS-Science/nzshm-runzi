from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel

    from runzi.automation.scaling.toshi_api import ModelType
    from runzi.execute.arguments import SystemArgs


def get_task_config(task_args: 'BaseModel', task_system_args: 'SystemArgs', model_type: 'ModelType') -> dict[str, Any]:
    """Package user inputs and generated system args into a dict for transport.

    Args:
        task_args: The arguments for the taks.
        task_system_args: The system arguments (contains the auto-generating inputs for a task).

    returns:
        A dictionary with keys 'task_args' and 'task_system_args' and values that are the output of
            model_dump() of the argument objects.
    """
    return dict(
        task_args=task_args.model_dump(mode='json'),
        task_system_args=task_system_args.model_dump(mode='json'),
        model_type=model_type.value,
    )
