"""
Build and store index of general tasks. Existing index is retrieved from S3, new data appended, and updated index
uploaded to S3.

Structure of index is: List[Dict[str,Any]]

"""
import argparse
import itertools
import json
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, Tuple

import boto3.session
from nzshm_common.location.code_location import CodedLocation
from nzshm_common.location.location import location_by_id
from nzshm_common.util import compress_string, decompress_string

from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_REPORT_BUCKET, S3_URL, WORK_PATH
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


def coded_location(loc: Tuple[float, float]) -> CodedLocation:
    return CodedLocation(*loc, 0.001).code


def requested_configs(
    locations: List[Tuple[float, float]],
    deagg_agg_targets: List[str],
    poes: List[float],
    imts: List[str],
    vs30s: List[int],
    deagg_hazard_model_target: str,
    inv_time: int,
    iter_method: str = ''
) -> Generator[DeaggConfig, None, None]:

    if not iter_method or iter_method.lower() == 'product':
        iterator = itertools.product(
            map(coded_location, locations),
            deagg_agg_targets,
            poes,
            imts,
            vs30s,
        )
    elif iter_method.lower() == 'zip':
        iterator = zip(
            map(coded_location, locations),
            deagg_agg_targets,
            poes,
            imts,
            vs30s,
        )
    else:
        raise ValueError('iter_method must be empty, "product", or "zip", %s given.' % iter_method)

    for location, agg, poe, imt, vs30 in iterator:
        yield DeaggConfig(
            hazard_model_id=deagg_hazard_model_target,
            location=location,
            inv_time=inv_time,
            agg=agg,
            poe=poe,
            imt=imt,
            vs30=vs30,
        )


def get_deagg_gtids(
    hazard_gts: List[str],
    locations: List[Tuple[float, float]],
    deagg_agg_targets: List[str],
    poes: List[float],
    imts: List[str],
    vs30s: List[int],
    deagg_hazard_model_target: str,
    inv_time: int,
    iter_method: str = '',
) -> List[str]:
    
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

    if hazard_gts:
        return hazard_gts
    else:
        gtids = []
        index = get_index_from_s3()
        for deagg in requested_configs(
            locations, deagg_agg_targets, poes, imts, vs30s, deagg_hazard_model_target, inv_time, iter_method,
        ):
            gtids_tmp = []
            for gt, entry in index.items():
                if entry['subtask_type'] == 'OpenquakeHazardTask' and entry['hazard_subtask_type'] == 'DISAGG':
                    if deagg == extract_deagg_config(entry['subtasks'][0]):
                        gtids_tmp.append(entry['id'])
            if not gtids_tmp:
                raise Exception("no general task found for deagg {}".format(deagg))
            if len(gtids_tmp) > 1:
                raise Exception("more than one general task {} found for {}".format(gtids_tmp, deagg))
            gtids += gtids_tmp

    return gtids


def parse_args():
    parser = argparse.ArgumentParser(description="add general task and subtasks to index")
    parser.add_argument("--force", action="store_true")
    group = parser.add_mutually_exclusive_group(required=True) 
    group.add_argument("--add-ids", nargs="+", help="list of GeneralTask IDs to add to index")
    group.add_argument("--remove", nargs="+", help="remove GT IDs rather than adding to the index")
    group.add_argument("--read", action="store_true", help="read stored index")
    group.add_argument("--reset", action="store_true", help="clear the index. WARNING: THIS CANNOT BE UNDONE")
    group.add_argument("--convert", action="store_true", help="one-time conversion of index from old to new format")
    group.add_argument("--list-ids", action="store_true", help="list the ids in the index")
    group.add_argument("--list-disaggs", action="store_true", help="list the disaggregations stored in the index")
    group.add_argument(
        "--find-disaggs", type=str,
        help="""find a specific disaggregations matching
        hazard_model_id= NSHM_v1.0.4, location=-39.500~176.900, inv_time=50, agg=mean, poe=0.02, imt=PGA, vs30=200"""
    )
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
        task['hazard_subtask_type'] = 'DISAGG'  # workaround because the disagg task is setting the incorrect subtask_type (temporary)
        # task['hazard_subtask_type'] = haz_task_type
    
    entry = dict(
        subtask_type = task['subtask_type'],
        hazard_subtask_type = task['hazard_subtask_type'],
        arguments = task['subtasks'][0]['arguments'],
        num_success = get_num_success_old(task)
    )
    entry['arguments'].update(convert_args_to_old(entry))

    return entry

def write_index(index, index_filepath):
    index_comp = compress_string(json.dumps(index))
    with open(index_filepath, 'w') as index_file:
        index_file.write(index_comp)

def save_index(index):
    # save index as serialized json file

    with tempfile.TemporaryDirectory() as index_dir:
        index_filepath = Path(index_dir, 'gt-index.json')
        write_index(index, index_filepath)
        # index_comp = compress_string(json.dumps(index))
        # with open(index_filepath, 'w') as index_file:
        #     # json.dump(index, index_file)
        #     index_file.write(index_comp)

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
    
    if len(ids) == 1 and Path(ids[0]).exists():
        ids = read_ids_from_file(ids[0])

    for gt_id in ids:
        del index[gt_id]
    return index


def read_ids_from_file(ids_filepath):

    with open(ids_filepath, 'r') as ids_file:
        return list(map(str.strip, ids_file.readlines()))

def append_gts(index, ids, force=False):

    if len(ids) == 1 and Path(ids[0]).exists():
        ids = read_ids_from_file(ids[0])

    for gt_id in ids:
        if index.get(gt_id) and not force:
            raise Exception(f"GT ID {gt_id} already exists in the index")
        index[gt_id] = get_tasks(gt_id)

    return index

# def convert_index(index):
    
    # new_index = {}
    # for entry in index:
    #     new_index[entry['id']]  = entry
    # return new_index

def clean_json_str(string):
    return string.replace("'", '"').replace('None', 'null')


def convert_args_to_old(entry):
    location = json.loads(clean_json_str(entry['arguments']['location_list']))[0]
    inv_time = int(entry['arguments']['inv_time'])
    poe = float(entry['arguments']['poe'])
    imt = entry['arguments']['imt']
    vs30 = int(entry['arguments']['vs30'])
    hazard_model_id = entry['arguments']['description'][15:]
    hazard_agg_target = entry['arguments']['agg']
    
    deagg_task_config = dict(
        location=location,
        inv_time=inv_time,
        poe=poe,
        imt=imt,
        vs30=vs30,
    )

    args_old = dict(
        disagg_config=json.dumps(deagg_task_config),
        hazard_model_id=hazard_model_id,
        hazard_agg_target=hazard_agg_target,
    )

    return args_old


def extract_deagg_config(entry):
    deagg_task_config = json.loads(entry['arguments']['disagg_config'].replace("'", '"').replace('None', 'null'))

    return DeaggConfig(
        hazard_model_id=entry['arguments']['hazard_model_id'],
        location=deagg_task_config['location'],
        inv_time=deagg_task_config['inv_time'],
        agg=entry['arguments']['hazard_agg_target'],
        poe=deagg_task_config['poe'],
        imt=deagg_task_config['imt'],
        vs30=deagg_task_config['vs30'],
    )

def get_num_success_old(gt):
    count = 0
    for subtask in gt['subtasks']:
        if subtask['result'] == 'SUCCESS':
            count += 1
    return count

def get_num_success(gt):
    return gt['num_success']

def list_disaggs(index):

    for gt_id, entry in index.items():
        if entry['subtask_type'] == 'OpenquakeHazardTask' and entry['hazard_subtask_type'] == 'DISAGG':
            disagg_config = extract_deagg_config(entry)
            num_success = get_num_success(entry)
            print(f"id: {gt_id}")
            print(f"number of successful subtaks: {num_success}")
            print(disagg_config)
            print('-' * 50)
            print('')

def find_disaggs(index, search_str):
    """
    hazard_model_id= NSHM_v1.0.4, location=-39.500~176.900, inv_time=50, agg=mean, poe=0.02, imt=PGA, vs30=200
    """
    search_str = "".join(search_str.split())
    kv = lambda x: x.split("=")
    search_terms = {kv(item)[0]: kv(item)[1] for item in search_str.split(",")}
    for gt_id , entry in index.items():
        match = True
        disagg_config = extract_deagg_config(entry)
        for search_key, search_value in search_terms.items():
            if search_key == "location" and ("~" not in search_value):
                sv = CodedLocation(location_by_id(search_value)['latitude'], location_by_id(search_value)['longitude'], 0.001).code
            else:
                sv = search_value
            if str(getattr(disagg_config, search_key)) != sv:
                match = False
                break
        if match:
            print(f"id: {gt_id}")
            print(disagg_config)
            print('-' * 50)
            print('')


def list_bad_disaggs(index, n_expected):
    for gt_id, entry in index.items():
        if n_expected != get_num_success(entry):
            disagg_config = extract_deagg_config(entry)
            num_success = get_num_success(entry)
            print(f"id: {gt_id}")
            print(f"number of successful subtaks: {num_success}")
            print(disagg_config)
            print('-' * 50)
            print('')

def convert_index(index):
    index_new = {k: dict(
            subtask_type = v['subtask_type'],
            hazard_subtask_type = v['hazard_subtask_type']
        )
    for k,v in index.items()
    }

    for k in index.keys():
        index_new[k]['arguments'] = index[k]['subtasks'][0]['arguments']
        index_new[k]['num_success'] = get_num_success_old(index[k])
    
    return index_new

def run(args):
    # index_filepath = Path(WORK_PATH, "gt-index", "gt-index.json")
    # if not index_filepath.parent.exists():
    #     index_filepath.parent.mkdir()
    
    index = get_index_from_s3()
    save = False 
    if args.list_ids:
        print(*index.keys(),sep='\n')
    elif args.find_disaggs:
        find_disaggs(index, args.find_disaggs)
    elif args.find_bad:
        list_bad_disaggs(index, args.find_bad)
    elif args.list_disaggs:
        list_disaggs(index)
    elif args.reset:
        save = True
        clear = input("WARNING: THIS WILL CLEAR ALL ENTRIES IN THE INDEX, DO YOU WANT TO PROCEED? [y/N]")
        if clear.lower() == "y":
            index = {}
    elif args.read:
        index_tmp = {}
        for i,(k,v) in enumerate(index.items()):
            if i>2:
                break
            index_tmp[k] = v

        json.dump(index_tmp, open('index_tmp.json', 'w'), indent=4)
        write_index(index, 'index.json')
        # print(index)
    elif args.remove:
        save = True
        proceed = input(f"WARNING: THIS WILL CLEAR ALL ENTRIES {args.remove} IN THE INDEX, DO YOU WANT TO PROCEED? [y/N]")
        if proceed.lower() == "y":
            index = remove_gts(index, args.remove)
    elif args.convert:
        save = True
        index = convert_index(index)
        # write_index(index_new, "/home/chrisdc/tmp/index_new.json")
        # index = convert_index(index)
    elif args.add_ids:
        save = True
        index = append_gts(index, args.add_ids, args.force)

    if save: 
        save_index(index)


if __name__ == "__main__":
    run(parse_args())