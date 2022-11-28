#run_oq_disagg_post.py
#!python3
"""
This script compiles a json file for a given GT id / json cnfig.

"""
import argparse
import logging
import json
import datetime as dt
from pathlib import Path
from zipfile import ZipFile

from nshm_toshi_client.toshi_client_base import ToshiClientBase
from nshm_toshi_client.toshi_file import ToshiFile
from runzi.automation.scaling.local_config import (API_KEY, API_URL, WORK_PATH)

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, API_KEY, API_URL, EnvMode )

class DisaggDetails(ToshiClientBase):

    def __init__(self, url, s3_url, auth_token, with_schema_validation=False, headers=None ):
        super().__init__(url, auth_token, with_schema_validation, headers)
        self._s3_url = s3_url

    def get_dissag_detail(self, general_task_id):
        qry = '''
        query disagg_gt ($general_task_id:ID!) {
            node1: node(id: $general_task_id) {
            id
            ... on GeneralTask {
              subtask_count
              children {
                total_count
                edges {
                  node {
                    child {
                      ... on OpenquakeHazardTask {
                        arguments {k v}
                        result
                        hazard_solution {
                          id
                          csv_archive { id }
                          hdf5_archive { id }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        '''

        print(qry)
        input_variables = dict(general_task_id=general_task_id)
        executed = self.run_query(qry, input_variables)
        return executed


def get_enriched_details(disagg_info):
    for task in disagg_info['children']['edges']:
        for itm in task['node']['child']['arguments']:
            if itm['k'] == 'disagg_config':
                #print( itm['v'] )
                obj = json.loads(itm['v'].replace("'", '"'))
                obj['hazard_solution_id'] = task['node']['child']['hazard_solution']['id']
                obj['hazard_solution_csv_archive_id'] = task['node']['child']['hazard_solution']['csv_archive']['id']
                obj['hazard_solution_hdf5_archive_id'] = task['node']['child']['hazard_solution']['hdf5_archive']['id']

                obj['hazard_solution_url'] = TOSHI_UI_URL + '/HazardSolution/'  + obj['hazard_solution_id']
                obj['hazard_solution_csv_archive_url'] = TOSHI_UI_URL + '/FileDetail/' + obj['hazard_solution_csv_archive_id']
                obj['hazard_solution_hdf5_archive_url'] = TOSHI_UI_URL + '/FileDetail/' + obj['hazard_solution_hdf5_archive_id']

                yield(obj)


# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1
# USE_API = False

def check_result(disagg_info):

  edges = disagg_info['data']['node1']['children']['edges']
  success_count = 0
  for edge in edges:
    if edge['node']['child']['result'] == 'SUCCESS': success_count += 1
  return success_count


if __name__ == "__main__":

  TOSHI_UI_URL = 'http://simple-toshi-ui.s3-website-ap-southeast-2.amazonaws.com' #PROD

  parser = argparse.ArgumentParser(description="""produce a zip archive of openquake configuration inputs
and save this as a ToshiAPI File object""")
  parser.add_argument("run_output", help="the path to the file containing the GT IDs of the oq disagg runs (e.g. `python runzi/automation/run_oq_disagg.py > disagg.out`")
  parser.add_argument("out_dir", help="the path of the output directory")
  args = parser.parse_args()
  gt_filepath = args.run_output
  output_dir = Path(args.out_dir)
  if not output_dir.exists():
    output_dir.mkdir()

  gt_ids = []
  with open(gt_filepath,'r') as gt_file:
    for line in gt_file.readlines():
      if 'GENERAL_TASK_ID' in line:
        gt_ids.append(line[17:].strip())
  gt_ids = set(gt_ids)
  
  
  
  
  headers={"x-api-key":API_KEY}
  disagg_api = DisaggDetails(API_URL, None, None, with_schema_validation=False, headers=headers)
  gt_data_filenames = []
  for gt_id in gt_ids:
    disagg_info = {}
    disagg_info['data'] = disagg_api.get_dissag_detail(gt_id)
    success_count = check_result(disagg_info)
    if not (success_count == 49) | (success_count == 46): #| (success_count == 40) :
      # arguments = disagg_info['data']['node1']['children']['edges'][0]['node']['child']['arguments']
      # raise Exception('GT ID %s got %s sucessfull jobs for %s' % (gt_id, success_count, arguments ))

    # # if success_count == 40:
      arguments = disagg_info['data']['node1']['children']['edges'][0]['node']['child']['arguments']
      print('='*50)
      print('GT ID %s got %s sucessfull jobs for %s' % (gt_id, success_count, arguments ))
      print(' ')

    disagg_result = dict(general_task_id=gt_id, deagg_solutions = disagg_info)
    gt_datafile = Path(output_dir,f'disagg_result_{gt_id}.json')
    with gt_datafile.open(mode='w') as f:
      gt_data_filenames.append(gt_datafile)
      f.write(json.dumps(disagg_result, indent=4))

  with Path(output_dir,'gtdata_files.list').open(mode='w') as f:
    for gt in gt_data_filenames:
      f.write('"' + str(gt) + '", ')

  with ZipFile(Path(output_dir, 'disagg_gt_data.zip'),'w') as gtzip:
    for gt in gt_data_filenames:
      gtzip.write(gt,arcname=gt.name)

  print('Done!')