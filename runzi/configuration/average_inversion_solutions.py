from hashlib import new
import os
import stat
import base64
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

        common_rupture_set = get_common_rupture_set(source_solution_ids,toshi_api)
      
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
                common_rupture_set=common_rupture_set
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
        


def get_common_rupture_set(source_solution_ids,toshi_api):

    rupture_set_id = ''
    for source_solution_id in source_solution_ids:

        new_rupture_set_id = get_rupture_set_id(source_solution_id,toshi_api)
        if not rupture_set_id:
            rupture_set_id = new_rupture_set_id
        else:
            if new_rupture_set_id == rupture_set_id:
                continue
            else:
                raise Exception(f'source objects {source_solution_ids} do not have consistant rupture sets')
    
    return rupture_set_id

        


def get_rupture_set_id(source_solution_id,toshi_api):

    # I'm going to assume we can always use predecessors, 
    # it should always be the case in the future and backwards 
    # compatability is a bit of a pain to write

    rupture_set_id = get_rupture_set_from_predecessors(source_solution_id,toshi_api)
    
    if not rupture_set_id:
        raise Exception(f'cannot find rupture set for {source_solution_id}')

    return rupture_set_id
        

        
def get_rupture_set_from_predecessors(source_solution_id,toshi_api):
    
    rupture_set_id = ''
    
    # it's possible there are multiple oldest predecessors (if for some reason the user is 
    # calculating the average of average), so check them all
    # I'm assuming that if typename is 'File' then the object is a rupture set
    predecessors = toshi_api.get_predecessors(source_solution_id)
    
    if predecessors:
        oldest_depth = min( [pred['depth'] for pred in predecessors] )
        oldest_ids = [pred['id'] for pred in predecessors if pred['depth'] == oldest_depth]
        
        
        for id in oldest_ids:
            if (is_rupture_set(id)) and (not rupture_set_id):
                rupture_set_id = id
            elif is_rupture_set(id):
                if rupture_set_id == id:
                    continue
                else:
                    raise Exception(f'object with ID {source_solution_id} comes from multiple rupture sets')

    return rupture_set_id


def is_rupture_set(id):
    return "'File:" in str(base64.b64decode(id))


