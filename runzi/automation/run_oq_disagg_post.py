"""
This script compiles a json file for a given GT id / json cnfig.

"""

import argparse
import csv
import os
from collections import namedtuple
from pathlib import Path

from nshm_toshi_client.toshi_client_base import ToshiClientBase

from runzi.automation.scaling.local_config import API_KEY, API_URL

DISAGG_LIST = os.environ['NZSHM22_DISAGG_LIST']


class DisaggDetails(ToshiClientBase):

    def __init__(self, url, s3_url, auth_token, with_schema_validation=False, headers=None):
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


def check_result(disagg_info):

    edges = disagg_info['node1']['children']['edges']
    success_count = 0
    for edge in edges:
        if edge['node']['child']['result'] == 'SUCCESS':
            success_count += 1
    return success_count


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="""append batch of disagg runs to the master list $NZSHM22_DISAGG_LIST
              and check that correct number of subtasks succeeded"""
    )
    parser.add_argument("disagg_run_output", help="the path to the output file from run_oq_disagg.py")
    args = parser.parse_args()
    gt_filepath = args.disagg_run_output
    if not Path(gt_filepath).exists():
        raise Exception("file %s does not exist" % gt_filepath)

    headers = {"x-api-key": API_KEY}
    disagg_api = DisaggDetails(API_URL, None, None, with_schema_validation=False, headers=headers)
    with open(gt_filepath, 'r') as gt_file:
        gt_reader = csv.reader(gt_file)
        with open(DISAGG_LIST, 'a') as list_file:
            writer = csv.writer(list_file)
            Disagg = namedtuple("Disagg", next(gt_reader), rename=True)
            for row in gt_reader:
                disagg = Disagg(*row)
                gt_id = disagg.GT_ID

                disagg_info = disagg_api.get_dissag_detail(gt_id)
                success_count = check_result(disagg_info)

                if not (success_count == 49):
                    row_out = list(disagg) + ['N', str(success_count)]
                else:
                    row_out = list(disagg) + ['Y', str(success_count)]

                writer.writerow(row_out)

    print('Done!')
