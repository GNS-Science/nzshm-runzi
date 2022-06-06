
import datetime as dt
from dateutil.tz import tzutc
from hashlib import md5
from pathlib import PurePath
from enum import Enum
import logging

import base64
import copy
import json
import requests

from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql

log = logging.getLogger(__name__)

class InversionSolutionNrml(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def upload_inversion_solution_nrml(self, task_id, source_solution_id, filepath,
        predecessors=None,
        meta=None,  metrics=None):
        filepath = PurePath(filepath)
        file_id, post_url = self._create_inversion_solution_nrml(filepath, task_id, source_solution_id, predecessors, meta, metrics)
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

    def _create_inversion_solution_nrml(self, filepath, produced_by, source_solution, predecessors=None, meta=None, metrics=None):
        """test helper"""
        query = '''
            mutation ($source_solution: ID!, $digest: String!, $file_name: String!, $file_size: BigInt!, $created: DateTime!, $predecessors: [PredecessorInput]) {
              create_inversion_solution_nrml(
                  input: {
                      source_solution: $source_solution
                      # produced_by: $produced_by
                      md5_digest: $digest
                      file_name: $file_name
                      file_size: $file_size
                      created: $created
                      predecessors: $predecessors


                      ##META##

                  }
              )
              {
                ok
                inversion_solution_nrml { id, file_name, file_size, md5_digest, post_url, 
                source_solution { ... on Node { id } }}
              }
            }
            '''

        if meta:
            query = query.replace("##META##", kvl_to_graphql('meta', meta))

        
        filedata = open(filepath, 'rb')
        digest = base64.b64encode(md5(filedata.read()).digest()).decode()
        filedata.seek(0) #important!
        size = len(filedata.read())
        filedata.close()

        created = dt.datetime.now(tzutc()).isoformat()
        variables = dict(digest=digest, file_name=filepath.parts[-1], file_size=size,
          produced_by=produced_by, source_solution=source_solution, created=created, predecessors=predecessors)

        executed = self.api.run_query(query, variables)
        # print("executed", executed)
        post_url = json.loads(executed['create_inversion_solution_nrml']['inversion_solution_nrml']['post_url'])
        return (executed['create_inversion_solution_nrml']['inversion_solution_nrml']['id'], post_url)
