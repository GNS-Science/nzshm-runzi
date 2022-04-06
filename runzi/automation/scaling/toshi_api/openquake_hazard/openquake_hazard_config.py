
from datetime import datetime as dt
from dateutil.tz import tzutc
from hashlib import md5
from pathlib import PurePath

import base64
import json
import requests

from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql

import logging
log = logging.getLogger(__name__)

class OpenquakeHazardConfig(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def upload_hazard_config(self, task_id, source_models, filepath):
        filepath = PurePath(filepath)
        file_id, post_url = self._create_hazard_configuration(filepath, task_id, source_models)
        self.upload_content(post_url, filepath)

        # #link file to task in role
        # self.api.task_file.create_task_file(task_id, file_id, 'WRITE')
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

    def _create_hazard_configuration(self, filepath, source_models, produced_by):
        qry = '''
            mutation ($created: DateTime!, $source_models: [ID!], $digest: String!,
                $file_name: String!, $file_size: Int!, $produced_by: ID!) {
              create_openquake_hazard_config(input: {
                  created: $created
                  source_models: $sources #must be NRML sources Openquake
                  md5_digest: $digest
                  file_name: $file_name
                  file_size: $file_size
                  produced_by_id: $produced_by
                  ##MFD_TABLE##

                  ##META##

                  ##METRICS##

                  }
              ) {
              config { id, created, source_models { id } }
              }
            }
        '''

        filedata = open(filepath, 'rb')
        digest = base64.b64encode(md5(filedata.read()).digest()).decode()

        filedata.seek(0) #important!
        size = len(filedata.read())
        filedata.close()

        created = dt.utcnow(tzutc()).isoformat()
        variables = dict(digest=digest, source_models=source_models, file_name=filepath.parts[-1], file_size=size,
          produced_by=produced_by, created=created)

        #result = self.api.client.execute(qry, variable_values = variables)
        #print(result)
        executed = self.api.run_query(qry, variables)
        #print("executed", executed)
        post_url = json.loads(executed['create_inversion_solution']['inversion_solution']['post_url'])

        return (executed['create_inversion_solution']['inversion_solution']['id'], post_url)


    def get_hazard_config(self, config_id):

        qry = '''
        query get_hazard_config ($config_id: ID!) {
          node(id:$config_id) {
            __typename
            ... on OpenquakeHazardConfig{
              created
              file_name
              file_url
              file_size
              # source_models {
              #   id
              #   source_solution {
              #       id
              #       file_name
              #   }
              # }
            }
          }
        }
        }
        '''

        executed = self.api.run_query(qry, dict(config_id=config_id))
        return executed['node']