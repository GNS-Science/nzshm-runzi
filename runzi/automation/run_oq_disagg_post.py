#run_oq_disagg_post.py
#!python3
"""
This script compiles a json file for a given GT id / json cnfig.

"""
import logging
import json
import datetime as dt

from nshm_toshi_client.toshi_client_base import ToshiClientBase
from nshm_toshi_client.toshi_file import ToshiFile

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, API_KEY, API_URL, EnvMode )

class DisaggDetails(ToshiClientBase):

    def __init__(self, url, s3_url, auth_token, with_schema_validation=False, headers=None ):
        super().__init__(url, auth_token, with_schema_validation, headers)
        self._s3_url = s3_url

    def get_dissag_detail(self, general_task_id):
        qry = '''
        query disagg_gt ($general_task_id:ID!) {
            node(id: $general_task_id) {
            __typename
            id
            ... on GeneralTask {
              subtask_count
              children {
                edges {
                  node {
                    child {
                      ... on OpenquakeHazardTask {
                        arguments {k v}
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
        return executed['node']


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


if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('gql.transport').setLevel(logging.WARN)
    log = logging.getLogger(__name__)

    GENERAL_TASK_ID = 'R2VuZXJhbFRhc2s6MTA4NzEz' # PROD
    #GENERAL_TASK_ID = 'R2VuZXJhbFRhc2s6MTAxNDQy' # TEST
    TOSHI_UI_URL = 'http://simple-toshi-ui.s3-website-ap-southeast-2.amazonaws.com' #PROD

    # CONFIG_FILE = "/GNSDATA/APP/nzshm-runzi/runzi/CONFIG/DISAGG/disagg_full_logictree.json"
    # with open(CONFIG_FILE, 'r') as df:
    #     disagg_configs = json.loads(df.read())

    headers={"x-api-key":API_KEY}


    # BUILD a query for fetch meta from GT subtasks
    # for each subtask, append to config_file...
    # the meta from  te
    # - hazard_solution_toshi_url
    # - hazard_solution_csv_archive_url
    # - hazard_solution_hdf5_archive_url
    # Write out the modified config file

    disagg_api = DisaggDetails(API_URL, None, None, with_schema_validation=False, headers=headers)
    disagg_info = disagg_api.get_dissag_detail(GENERAL_TASK_ID)

    disagg_solutions=[]
    for o in get_enriched_details(disagg_info):
        disagg_solutions.append(o)

    disagg_result = dict(general_task_id=GENERAL_TASK_ID, hazard_solutions = disagg_solutions)
    with open('disagg_result.json', 'w') as f:
        f.write(json.dumps(disagg_result, indent=4))

    print('Done!')