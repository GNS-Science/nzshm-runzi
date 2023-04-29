"""
Build and store index of general tasks. Existing index is retrieved from S3, new data appended, and updated index
uploaded to S3.

Structure of index is: List[Dict[str,Any]]

"""
import argparse
from dataclasses import dataclass
import json
import boto3.session
import urllib.request
import tempfile
from pathlib import Path

from nzshm_common.util import compress_string, decompress_string

from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, S3_REPORT_BUCKET)
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.util.aws.s3_folder_upload import mimetype

INDEX_URL = "https://nzshm22-static-reports.s3.ap-southeast-2.amazonaws.com/gt-index/gt-index.json"

headers = {"x-api-key": API_KEY}
toshi_api = ToshiApi(
    API_URL, S3_URL, None, with_schema_validation=True, headers=headers
)

@dataclass
class DeaggConfig:
    """class for specifying a deaggregation to lookup in GT index"""

    hazard_model_id: str
    location: str
    inv_time: int
    agg: str
    poe: float
    imt: str
    vs30: int

    def __repr__(self) -> str:
        repr = ''
        for k,v in self.__dict__.items():
            repr += f"{k}={v}\n"
        repr = repr[:-1]
        return repr

def parse_args():
    parser = argparse.ArgumentParser(description="add general task and subtasks to index")
    group = parser.add_mutually_exclusive_group(required=True) 
    group.add_argument("--add-ids", nargs="+", help="list of GeneralTask IDs to add to index")
    group.add_argument("--remove", nargs="+", help="remove GT IDs rather than adding to the index")
    group.add_argument("--read", action="store_true", help="read stored index")
    group.add_argument("--reset", action="store_true", help="clear the index. WARNING: THIS CANNOT BE UNDONE")
    group.add_argument("--convert", action="store_true", help="one-time conversion of index from old to new format")
    group.add_argument("--list-ids", action="store_true", help="list the ids in the index")
    group.add_argument("--list-disaggs", action="store_true", help="list the disaggregations stored in the index")
    group.add_argument("--find-bad", type=int, help="list the disaggregations with failed subtaks, specify number expected")
    args = parser.parse_args()

    return args


def get_index_from_s3():
    index_request = urllib.request.Request(INDEX_URL)
    index_str = urllib.request.urlopen(index_request)
    index_comp = index_str.read().decode("utf-8")
    return json.loads(decompress_string(index_comp))
    # return json.loads(index_str.read().decode("utf-8"))


def parse_task_args(args):
    if args:
        return {arg['k']: arg['v'] for arg in args}
    return {}

def parse_oqhazard_task(id):
    qry = """
        query oqht ($id:ID!) {
            node(id: $id) {
                ... on OpenquakeHazardTask {
                        created
                        state
                        result
                        task_type
                        arguments {
                            k v
                        }
                        hazard_solution {
                            id
                        }
                    }
            }
        }"""
    
    input_variables = dict(id=id)
    subtask = toshi_api.run_query(qry, input_variables)['node']
    subtask["subtask_type"] = "OpenquakeHazardTask"
    subtask["arguments"] = parse_task_args(subtask.pop("arguments"))
    return subtask


def get_subtask_info(subtask):
    
    subtask_type = subtask.pop("__typename")
    if subtask_type != "OpenquakeHazardTask":
        subtask["subtask_type"] = subtask_type
        subtask["arguments"] = parse_task_args(subtask.pop("arguments"))
        return subtask
    return parse_oqhazard_task(subtask['id'])


def get_tasks(gt_id):
    # query toshiapi on requested GT IDs for GT data and subtasks
    # query subtasks for data depending on subtask type
    
    task = toshi_api.get_general_task_subtasks(gt_id)
    typename = task.pop("__typename")
    if typename != "GeneralTask":
        raise Exception("task ID must be for a GeneralTask")
    task['subtasks'] = []
    children = task.pop("children")['edges']
    for child in children:
        task['subtasks'].append(get_subtask_info(child['node']['child']))
    task['subtask_type'] = task['subtasks'][0]['subtask_type']
    if haz_task_type := task['subtasks'][0]['task_type']:
        task['hazard_subtask_type'] = haz_task_type
    return task

def save_index(index):
    # save index as serialized json file

    with tempfile.TemporaryDirectory() as index_dir:
        index_filepath = Path(index_dir, 'gt-index.json')
        index_comp = compress_string(json.dumps(index))
        with open(index_filepath, 'w') as index_file:
            # json.dump(index, index_file)
            index_file.write(index_comp)

        # upload to S3
        session = boto3.session.Session()
        client = session.client('s3')
        try:
            client.upload_file(index_filepath, S3_REPORT_BUCKET, "gt-index/gt-index.json",
                ExtraArgs={
                    'ACL':'public-read',
                    'ContentType': mimetype(index_filepath)
                    })
            print("Uploading %s..." % S3_REPORT_BUCKET)
        except Exception as e:
            raise e


def remove_gts(index, ids):
    for id in ids:
        del index[id]
    return index


def read_ids_from_file(ids_filepath):

    with open(ids_filepath, 'r') as ids_file:
        return list(map(str.strip, ids_file.readlines()))

def append_gts(index, ids):

    if len(ids) == 1 and Path(ids[0]).exists():
        ids = read_ids_from_file(ids[0])

    for gt_id in ids:
        if index.get(gt_id):
            raise Exception(f"GT ID {gt_id} already exists in the index")
        index[gt_id] = get_tasks(gt_id)

    return index

def convert_index(index):
    
    new_index = {}
    for entry in index:
        new_index[entry['id']]  = entry
    return new_index

def extract_deagg_config(subtask):
        deagg_task_config = json.loads(subtask['arguments']['disagg_config'].replace("'", '"').replace('None', 'null'))

        return DeaggConfig(
            hazard_model_id=subtask['arguments']['hazard_model_id'],
            location=deagg_task_config['location'],
            inv_time=deagg_task_config['inv_time'],
            agg=subtask['arguments']['hazard_agg_target'],
            poe=deagg_task_config['poe'],
            imt=deagg_task_config['imt'],
            vs30=deagg_task_config['vs30'],
        )

def get_num_success(gt):
        count = 0
        for subtask in gt['subtasks']:
            if subtask['result'] == 'SUCCESS':
                count += 1
        return count

def list_disaggs(index):

    for gt_id, entry in index.items():
        if entry['subtask_type'] == 'OpenquakeHazardTask' and entry['hazard_subtask_type'] == 'DISAGG':
            disagg_config = extract_deagg_config(entry['subtasks'][0])
            num_success = get_num_success(entry)
            print(f"id: {gt_id}")
            print(f"number of successful subtaks: {num_success}")
            print(disagg_config)
            print('-' * 50)
            print('')


def list_bad_disaggs(index, n_expected):
    for gt_id, entry in index.items():
        if n_expected != get_num_success(entry):
            disagg_config = extract_deagg_config(entry['subtasks'][0])
            num_success = get_num_success(entry)
            print(f"id: {gt_id}")
            print(f"number of successful subtaks: {num_success}")
            print(disagg_config)
            print('-' * 50)
            print('')

def run(args):
    index_filepath = Path(WORK_PATH, "gt-index", "gt-index.json")
    if not index_filepath.parent.exists():
        index_filepath.parent.mkdir()
    
    index = get_index_from_s3()
    save = False 
    if args.list_ids:
        print(*index.keys(),sep='\n')
    elif args.find_bad:
        list_bad_disaggs(index, args.find_bad)
    elif args.list_disaggs:
        list_disaggs(index)
    elif args.reset:
        save = True
        clear = input("WARNING: THIS WILL CLEAR ALL ENTRIES IN THE INDEX, DO YOU WANT TO PROCEED? [y/N]")
        if clear.lower() == "y":
            index = []
    elif args.read:
        print(index)
    elif args.remove:
        save = True
        proceed = input(f"WARNING: THIS WILL CLEAR ALL ENTRIES {args.remove} IN THE INDEX, DO YOU WANT TO PROCEED? [y/N]")
        if proceed.lower() == "y":
            index = remove_gts(index, args.remove)
    elif args.convert:
        save = True
        index = convert_index(index)
    elif args.add_ids:
        save = True
        index = append_gts(index, args.add_ids)

    if save: 
        save_index(index)


if __name__ == "__main__":
    run(parse_args())