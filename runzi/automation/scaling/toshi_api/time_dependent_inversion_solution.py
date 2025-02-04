
import base64
import json
import logging
from datetime import datetime as dt
from hashlib import md5
from pathlib import PurePath

import requests
from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql

log = logging.getLogger(__name__)

class TimeDependentInversionSolution(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def upload_inversion_solution(self, task_id, filepath, source_solution_id, meta=None, predecessors=None):
        filepath = PurePath(filepath)
        file_id, post_url = self._create_inversion_solution(filepath, task_id, source_solution_id, meta, predecessors)
        self.upload_content(post_url, filepath)

        #link file to task in role
        self.api.task_file.create_task_file(task_id, file_id, 'WRITE')
        return file_id

    def upload_content(self, post_url, filepath):
        log.debug(f'upload_content() POST URL: {post_url}; PATH: {filepath}')
        filedata = open(filepath, 'rb')
        files = {'file': filedata}
        log.debug(f'upload_content() _s3_url: {self.api._s3_url}')

        response = requests.post(
            url=self.api._s3_url,
            data=post_url,
            files=files)
        log.debug(f'response {response}')
        response.raise_for_status()

    def _create_inversion_solution(self, filepath, produced_by, source_solution_id, meta=None, predecessors=None):
        qry = '''
            mutation ($source_solution: ID!, $created: DateTime!, $digest: String!, $file_name: String!, $file_size: BigInt!, $produced_by: ID!, $predecessors: [PredecessorInput]) {
              create_time_dependent_inversion_solution(input: {
                  source_solution: $source_solution
                  created: $created
                  md5_digest: $digest
                  file_name: $file_name
                  file_size: $file_size
                  produced_by: $produced_by
                  predecessors: $predecessors

                  ##META##

                  }
              ) {
              solution { id, post_url }
              }
            }
        '''

        if meta:
            qry = qry.replace("##META##", kvl_to_graphql('meta', meta))

        filedata = open(filepath, 'rb')
        digest = base64.b64encode(md5(filedata.read()).digest()).decode()
        # print('DIGEST:', digest)

        filedata.seek(0) #important!
        size = len(filedata.read())
        filedata.close()

        created = dt.utcnow().isoformat() + 'Z'
        variables = dict(source_solution=source_solution_id, digest=digest, file_name=filepath.parts[-1], file_size=size,
          produced_by=produced_by, created=created, predecessors=predecessors)

        executed = self.api.run_query(qry, variables)
        #print("executed", executed)
        post_url = json.loads(executed['create_time_dependent_inversion_solution']['solution']['post_url'])

        return (executed['create_time_dependent_inversion_solution']['solution']['id'], post_url)


    
    # def get_solution(self, solution_id):

    #     qry = '''
    #     query get_sol_tables ($solution_id: ID!) {
    #         node(id:$solution_id) {
    #           ... on InversionSolution {
    #             tables {
    #               source_solution
    #               created
    #               produced_by_id
    #               table_type
    #               identity
    #               table_id
    #             }
    #           }
    #         }
    #     }
    #     '''

    #     executed = self.api.run_query(qry, dict(solution_id=solution_id))
    #     return executed['node']

    
