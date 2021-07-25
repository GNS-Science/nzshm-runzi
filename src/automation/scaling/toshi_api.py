from datetime import datetime as dt
from hashlib import md5
from pathlib import PurePath

import base64
import copy
import json
import requests

from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql
from nshm_toshi_client.toshi_file import ToshiFile
from nshm_toshi_client.toshi_task_file import ToshiTaskFile


class ToshiApi(ToshiClientBase):

    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None ):
        super(ToshiApi, self).__init__(url, auth_token, with_schema_validation, headers)
        self._s3_url = s3_url

        self.file = ToshiFile(url, s3_url, auth_token, with_schema_validation, headers)
        self.task_file = ToshiTaskFile(url, auth_token, with_schema_validation, headers)

        #set up the handler for inversion_solution operations
        self.inversion_solution = InversionSolution(self)


    def get_general_task_subtask_files(self, id):
        return self.get_subtask_files(id)

    def get_subtask_files(self, id):
        gt = self.get_general_task_subtasks(id)
        for subtask in gt['children']['edges']:
            sbt = self.get_rgt_files(subtask['node']['child']['id'])
            subtask['node']['child']['files'] = copy.deepcopy(sbt['files'])
            #TESTING
            #break
        return gt

    def get_general_task_subtasks(self, id):
        qry = '''
            query one_general ($id:ID!)  {
              node(id: $id) {
                __typename
                ... on GeneralTask {
                  id
                  title
                  description
                  created
                  children {
                    #total_count
                    edges {
                      node {
                        child {
                          __typename
                          ... on Node {
                            id
                          }
                          ... on RuptureGenerationTask {
                            created
                            state
                            result
                            arguments {k v}
                          }
                        }
                      }
                    }
                  }
                }
              }
            }'''

        # print(qry)
        input_variables = dict(id=id)
        executed = self.run_query(qry, input_variables)
        return executed['node']

    def get_rgt_files(self, id):

        qry = '''
            query ($id:ID!) {
              node(id: $id) {
                __typename
                ... on RuptureGenerationTask {
                  id
                  files {
                    total_count
                    edges {
                      node {
                        ... on FileRelation {
                          role
                          file {
                            ... on Node {
                              id
                            }
                            ... on FileInterface {
                              file_name
                              file_size
                              meta {k v}
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

        # print(qry)
        input_variables = dict(id=id)
        executed = self.run_query(qry, input_variables)
        return executed['node']

    def get_file_detail(self, id):
        qry = '''
        query file ($id:ID!) {
                node(id: $id) {
            __typename
            ... on Node {
              id
            }
            ... on FileInterface {
              file_name
              file_size
              meta {k v}
            }
          }
        }'''

        print(qry)
        input_variables = dict(id=id)
        executed = self.run_query(qry, input_variables)
        return executed['node']


    def get_file_download_url(self, id):
        qry = '''
        query download_file ($id:ID!) {
                node(id: $id) {
            __typename
            ... on Node {
              id
            }
            ... on FileInterface {
              file_name
              file_size
              file_url
            }
          }
        }'''

        print(qry)
        input_variables = dict(id=id)
        executed = self.run_query(qry, input_variables)
        return executed['node']



    def create_table(self, rows, column_headers, column_types, object_id, table_name, created=None):

        created = created or dt.utcnow().isoformat() + 'Z'

        rowlen = len(column_headers)
        assert len(column_types) == rowlen
        for t in column_types:
            assert t in "string,double,integer,boolean".split(',')
        for row in rows:
            assert len(row) == rowlen
            #when do we check the coercions??

        input_variables = {
          "headers": column_headers,
          "object_id": object_id,
          "rows": rows,
          "column_types": column_types,
          "table_name": table_name,
          "created": created
        }

        qry = '''
        mutation create_table ($rows: [[String]]!, $object_id: ID!, $table_name: String!, $headers: [String]!, $column_types: [RowItemType]!, $created: DateTime!) {
          create_table(input: {
            name: $table_name
            created: $created
            object_id: $object_id
            column_headers: $headers
            column_types: $column_types
            rows: $rows
            })
          {
            table {
              id
            }
          }
        }'''

        #print(qry)
        executed = self.run_query(qry, input_variables)
        return executed['create_table']['table']

class InversionSolution(object):

    def __init__(self, api):
        self.api = api

    def upload_inversion_solution(self, task_id, filepath, mfd_table, meta=None,  metrics=None):
        filepath = PurePath(filepath)
        file_id, post_url = self._create_inversion_solution(filepath, task_id, mfd_table, meta, metrics)
        self.upload_content(post_url, filepath)

        #link file to task in role
        return self.api.task_file.create_task_file(task_id, file_id, 'WRITE')

    def upload_content(self, post_url, filepath):
        print('upload_content **** POST DATA %s' % post_url )
        filedata = open(filepath, 'rb')
        files = {'file': filedata}
        url = self.api._s3_url
        print('url', url)

        response = requests.post(
            url=url,
            data=post_url,
            files=files)
        print("REQUEST RESPONSE",  response)


    # def _upload_file(self, filepath, produced_by, mfd_table, meta=None):
    #     filepath = PurePath(filepath)
    #     file_id, post_url = self._create_inversion_solution(filepath, produced_by, mfd_table, meta)
    #     self.api.file.upload_content(post_url, filepath)
    #     return file_id

    def _create_inversion_solution(self, filepath, produced_by, mfd_table, meta=None, metrics=None):
        qry = '''
            mutation ($created: DateTime!, $digest: String!, $file_name: String!, $file_size: Int!, $produced_by: ID!, $mfd_table: ID!) {
              create_inversion_solution(input: {
                  created: $created
                  md5_digest: $digest
                  file_name: $file_name
                  file_size: $file_size
                  produced_by_id: $produced_by
                  mfd_table_id: $mfd_table

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


        print(qry)

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
        print("executed", executed)
        post_url = json.loads(executed['create_inversion_solution']['inversion_solution']['post_url'])

        return (executed['create_inversion_solution']['inversion_solution']['id'], post_url)

