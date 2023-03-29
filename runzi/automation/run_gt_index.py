"""
Build and store index of general tasks. Existing index is retrieved from S3, new data appended, and updated index
uploaded to S3.

Structure of index is: List[Dict[str,Any]]

"""
import argparse
import json
import boto3.session
import urllib.request
from pathlib import Path

from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, S3_REPORT_BUCKET)
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.util.aws.s3_folder_upload import mimetype

INDEX_URL = "https://nzshm22-static-reports.s3.ap-southeast-2.amazonaws.com/gt-index/gt-index.json"

headers = {"x-api-key": API_KEY}
toshi_api = ToshiApi(
    API_URL, S3_URL, None, with_schema_validation=True, headers=headers
)

def parse_args():
    parser = argparse.ArgumentParser(description="add general task and subtasks to index")
    parser.add_argument("gt_ids", nargs="*", help="list of GeneralTask IDs to add to index")
    parser.add_argument("--read", action="store_true", help="read stored index")
    parser.add_argument("--reset", action="store_true", help="clear the index. WARNING: THIS CANNOT BE UNDONE")
    parser.add_argument("--remove", action="store_true", help="remove GT IDs rather than adding to the index")
    args = parser.parse_args()
    if not (args.gt_ids or args.read or args.reset or args.remove):
        parser.parse_args(['-h'])
    return args


def get_index_from_s3():
    index_request = urllib.request.Request(INDEX_URL)
    index_str = urllib.request.urlopen(index_request)
    return json.loads(index_str.read().decode("utf-8"))


def parse_task_args(args):
    arguments = {}
    for arg in args:
        arguments[arg['k']] = arg['v']
    return arguments

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

def save_index(index, index_filepath, url):
    # save index as serialized json file
    with open(index_filepath, 'w') as index_file:
        json.dump(index, index_file, indent=2)

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
    i_rmv = []
    for i, entry in enumerate(index):
        if entry['id'] in ids:
            i_rmv.append(i)
    i_rmv.sort()
    i_rmv.reverse()
    for i in i_rmv:
        del index[i]
    return index


def read_ids_from_file(ids_filepath):

    with open(ids_filepath, 'r') as ids_file:
        return list(map(str.strip, ids_file.readlines()))

def append_gts(index, ids):

    if len(ids) == 1 and Path(ids[0]).exists():
        ids = read_ids_from_file(ids[0])

    for gt_id in ids:
        index.append(get_tasks(gt_id))

    return index

def run(args):

    index_filepath = Path(WORK_PATH, "gt-index", "gt-index.json")
    if not index_filepath.parent.exists():
        index_filepath.parent.mkdir()
    
    index = get_index_from_s3()
    save = False 
    if args.reset:
        save = True
        clear = input("WARNING: THIS WILL CLEAR ALL ENTRIES IN THE INDEX, DO YOU WANT TO PROCEED? [y/N]")
        if clear.lower() == "y":
            index = []
    elif args.read:
        print(index)
    elif args.remove:
        save = True
        proceed = input(f"WARNING: THIS WILL CLEAR ALL ENTRIES {args.gt_ids} IN THE INDEX, DO YOU WANT TO PROCEED? [y/N]")
        if proceed.lower() == "y":
            index = remove_gts(index, args.gt_ids)
    else:
        save = True
        index = append_gts(index, args.gt_ids)

    if save: 
        save_index(index, index_filepath, S3_URL)


if __name__ == "__main__":
    run(parse_args())