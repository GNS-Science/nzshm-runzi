from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel

    from runzi.arguments import TaskRuntimeArgs
    from runzi.automation.toshi_api import ModelType


def get_task_config(
    task_args: 'BaseModel', task_runtime_args: 'TaskRuntimeArgs', model_type: 'ModelType'
) -> dict[str, Any]:
    """Package user inputs and per-task runtime args into a dict for transport to the worker.

    Args:
        task_args: The user arguments for the task.
        task_runtime_args: The per-task runtime context the worker needs (general_task_id, task_count,
            use_api, gateway port, java_threads, allocated_vcpu). Submission-only config is NOT included.

    returns:
        A dictionary with keys 'task_args', 'task_runtime_args', 'model_type'; the args values are the
            output of model_dump() of the argument objects.
    """
    return dict(
        task_args=task_args.model_dump(mode='json'),
        task_runtime_args=task_runtime_args.model_dump(mode='json'),
        model_type=model_type.value,
    )
