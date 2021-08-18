
from datetime import datetime as dt
from hashlib import md5
from pathlib import PurePath

import base64
import json
import requests

from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql


class InversionSolution(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def upload_inversion_solution(self, task_id, filepath, mfd_table=None, meta=None,  metrics=None):
        filepath = PurePath(filepath)
        file_id, post_url = self._create_inversion_solution(filepath, task_id, mfd_table, meta, metrics)
        self.upload_content(post_url, filepath)

        #link file to task in role
        self.api.task_file.create_task_file(task_id, file_id, 'WRITE')
        return file_id

    def upload_content(self, post_url, filepath):
        #print('upload_content **** POST DATA %s' % post_url )
        filedata = open(filepath, 'rb')
        files = {'file': filedata}
        url = self.api._s3_url
        #print('url', url)

        response = requests.post(
            url=url,
            data=post_url,
            files=files)
        print("upload_content POST RESPONSE", response, filepath)


    def _create_inversion_solution(self, filepath, produced_by, mfd_table=None, meta=None, metrics=None):
        qry = '''
            mutation ($created: DateTime!, $digest: String!, $file_name: String!, $file_size: Int!, $produced_by: ID!) {
              create_inversion_solution(input: {
                  created: $created
                  md5_digest: $digest
                  file_name: $file_name
                  file_size: $file_size
                  produced_by_id: $produced_by
                  ##MFD_TABLE##

                  ##META##

                  ##METRICS##

                  }
              ) {
              inversion_solution { id, post_url }
              }
            }
        '''

        if meta:
            qry = qry.replace("##META##", kvl_to_graphql('meta', meta))
        if metrics:
            qry = qry.replace("##METRICS##", kvl_to_graphql('metrics', metrics))
        if mfd_table:
            qry = qry.replace("##MFD_TABLE##", f'mfd_table_id: "{mfd_table}"')

        #print(qry)

        filedata = open(filepath, 'rb')
        digest = base64.b64encode(md5(filedata.read()).digest()).decode()
        # print('DIGEST:', digest)

        filedata.seek(0) #important!
        size = len(filedata.read())
        filedata.close()

        created = dt.utcnow().isoformat() + 'Z'
        variables = dict(digest=digest, file_name=filepath.parts[-1], file_size=size,
          produced_by=produced_by, mfd_table=mfd_table, created=created)

        #result = self.api.client.execute(qry, variable_values = variables)
        #print(result)
        executed = self.api.run_query(qry, variables)
        #print("executed", executed)
        post_url = json.loads(executed['create_inversion_solution']['inversion_solution']['post_url'])

        return (executed['create_inversion_solution']['inversion_solution']['id'], post_url)


    def append_hazard_table(self, inversion_solution_id, mfd_table_id, label, table_type, dimensions):
        qry = '''
            mutation ($input: AppendInversionSolutionTablesInput!) {
              append_inversion_solution_tables(input: $input)
               {
               ok
               inversion_solution {
                  id,
                  tables {
                    identity
                    table_id
                    table {
                     id
                    }
                  }
                }
              }
            }
        '''
        input_args = dict(id=inversion_solution_id, tables=[
            dict(label=label, table_id=mfd_table_id, table_type=table_type, dimensions=dimensions)])
        return self.api.run_query(qry, dict(input=input_args))
