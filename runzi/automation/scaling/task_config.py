from pydantic import BaseModel


def get_task_config(task_args: BaseModel, task_system_args: BaseModel) -> dict:
    """Package user inputs and generated system args into a dict for transport.

    Args:
        task_args: Any Pydantic model that contains the user inputs for a task.
        task_system_args: Any Pydantic model that contains the auto-generating inputs for a task.

    returns:
        A dictionary with keys 'task_args' and 'task_system_args' and values that are the output of
            model_dump() of the Pydantic model objects.
    """
    return dict(task_args=task_args.model_dump(mode='json'), task_system_args=task_system_args.model_dump(mode='json'))
