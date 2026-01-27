"""This module provides the runner class for scaling the rupture rates of inversions."""

import runzi.execute.scale_solution_task as task_module
from runzi.automation.scaling.toshi_api import SubtaskType
from runzi.execute.arguments import ArgSweeper, TaskLanguage
from runzi.runners.time_dependent_solution import get_model_type_from_all, get_solution_ids_from_id

from .runner import JobRunner


class ScaleSolutionJobRunner(JobRunner):
    """A class to run scale solution jobs."""

    def __init__(self, job_args: ArgSweeper):
        """Initialize the ScaleSolutionJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(job_args, task_module)

    def custom_setup(self):
        self.system_args.task_language = TaskLanguage.PYTHON
        self.system_args.job_name = "Runzi-automation-scale-solution"
        self.system_args.subtask_type = SubtaskType.SCALE_SOLUTION
        self.system_args.max_job_time_min = 10

        # convert GT IDs to swept IDs of inversion solutions
        solution_ids = []
        for task_args in self.job_args.get_tasks():
            solution_ids += get_solution_ids_from_id(task_args.source_solution_id)

        if len(solution_ids) > 1:
            self.job_args.prototype.source_solution_id = solution_ids[0]
            self.job_args.swept_args['source_solution_id'] = solution_ids

        # this has to be done after converting GT to inversion solution IDs
        self.system_args.model_type = get_model_type_from_all(self.job_args)
