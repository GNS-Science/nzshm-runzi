from pickle import FALSE

import runzi.automation.run_oq_convert_solution as convert_solution
import runzi.automation.run_scale_solution as scale_solution
from runzi.automation.scaling.file_utils import get_output_file_ids
from runzi.automation.scaling.local_config import API_KEY, API_URL
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api.general_task import ModelType

WORKER_POOL_SIZE = 2

if __name__ == "__main__":

    task = 'test all 2'

    if task == 'test all':
        scale = True
        task_title = "TEST"
        TASK_DESCRIPTION = """first run locally """
        model_type = ModelType.SUBDUCTION
        source_solution_ids = ["SW52ZXJzaW9uU29sdXRpb246MTAwNDk5", "SW52ZXJzaW9uU29sdXRpb246MTAwNTA3"]
        scales = [0.61, 1.34]
    elif task == 'test all 2':
        scale = True
        task_title = "TEST inv --> scale --> NRML workflow"
        TASK_DESCRIPTION = """first run locally """
        model_type = ModelType.SUBDUCTION
        source_solution_ids = ["SW52ZXJzaW9uU29sdXRpb246MTAwODYx"]
        scales = [
            0.61,
        ]
    elif task == 'test convert only':
        scale = False
        task_title = "TEST convert only"
        TASK_DESCRIPTION = """first run locally """
        model_type = ModelType.SUBDUCTION
        source_solution_ids = ["U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAwNjU3", "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAwNjU2"]

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    if scale:
        scale_gt_id = scale_solution.run(
            source_solution_ids, scales, model_type, task_title, TASK_DESCRIPTION, WORKER_POOL_SIZE
        )

        # get solution IDs from scaleGTID
        file_generator = get_output_file_ids(toshi_api, scale_gt_id)
        scaled_solution_ids = []
        for f in file_generator:
            scaled_solution_ids.append(f['id'])
        task_title = task_title + ' NRML'
    else:
        scaled_solution_ids = source_solution_ids

    convert_gt_id = convert_solution.run(
        scaled_solution_ids, model_type, task_title, TASK_DESCRIPTION, WORKER_POOL_SIZE
    )

    if scale:
        print('scale solution GT ID:', scale_gt_id)
    print('convert solution GT ID:', convert_gt_id)
