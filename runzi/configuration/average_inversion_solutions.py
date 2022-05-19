import os
import stat
from pathlib import PurePath

from itertools import chain

from runzi.automation.scaling.toshi_api import SubtaskType, ModelType, ToshiApi
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.automation.scaling.file_utils import download_files, get_output_file_id

import runzi.execute.average_solutions_task

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, CLUSTER_MODE, EnvMode )

def build_average_tasks(general_task_id: str, task_type: SubtaskType, model_type: ModelType, subtask_arguments, toshi_api: ToshiApi):

    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.average_solutions_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    for source_solution_ids in subtask_arguments['source_solution_groups']:
        
        task_count += 1

        file_generators = []
        for input_id in source_solution_ids:
            file_generators.append(get_output_file_id(toshi_api, input_id)) #for file by file ID

        source_solutions = download_files(toshi_api, chain(*file_generators), str(WORK_PATH), overwrite=False,
                                            skip_download=(CLUSTER_MODE == EnvMode['AWS']))
        
        task_arguments = dict(
                model_type = model_type.name
            )
        job_arguments = dict(
                task_id = task_count,
                source_solution_ids = list(source_solutions.keys()),
                source_solution_info = list(source_solutions.values()), #list of dict
                working_path=str(WORK_PATH),
                general_task_id=general_task_id,
                use_api = USE_API,
                )

        
        if CLUSTER_MODE == EnvMode['AWS']:
                    pass
        else:
            #write a config
            task_factory.write_task_config(task_arguments, job_arguments)
            script = task_factory.get_task_script()

            script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
            with open(script_file_path, 'w') as f:
                f.write(script)

            #make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
        


    