from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from runzi.execute.arguments import ArgBase, SystemArgs


def get_task_config(task_args: 'ArgBase', task_system_args: 'SystemArgs') -> dict[str, Any]:
    """Package user inputs and generated system args into a dict for transport.

    Args:
        task_args: The arguments for the taks.
        task_system_args: The system arguments (contains the auto-generating inputs for a task).

    returns:
        A dictionary with keys 'task_args' and 'task_system_args' and values that are the output of
            model_dump() of the argument objects.
    """
    return dict(task_args=task_args.model_dump(mode='json'), task_system_args=task_system_args.model_dump(mode='json'))
