from datetime import datetime as dt
from nshm_toshi_client.toshi_client_base import ToshiClientBase
import copy

class ToshiApi(ToshiClientBase):

    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None ):
        super(ToshiApi, self).__init__(url, auth_token, with_schema_validation, headers)
        self._s3_url = s3_url

    def OLD_get_general_task_subtask_files(self, id):
        raise("Don't use this, its too slow, use ")
        qry = '''
            query one_general ($id:ID!)  {
              node(id: $id) {
                __typename
                ... on GeneralTask {
                  title
                  description
                  created
                  children {
                    total_count
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
                            files {
                              total_count
                              edges {
                                node {
                                  role
                                  file {
                                    ... on File {
                                      id
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
                  }
                }
              }
            }'''

        # print(qry)
        input_variables = dict(id=id)
        executed = self.run_query(qry, input_variables)
        return executed

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
                            ... on File {
                              id
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
            ... on File {
              id
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
            ... on File {
              id
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

    def _upload_file(self, filepath, meta=None):
        filepath = PurePath(filepath)
        file_id, post_url = self.file_api.create_file(filepath, meta)
        self.file_api.upload_content(post_url, filepath)
        return file_id

    def link_task_file(self, task_id, file_id, task_role):
        return self.api.task_file_api.create_task_file(task_id, file_id, task_role)

    def upload_inversion_solution(self, task_id, filepath, task_role, meta=None):
        filepath = PurePath(filepath)
        file_id = self.upload_file(filepath, meta)
        #link file to task in role
        return self.link_task_file(task_id, file_id, task_role)

    def create_inversion_solution(self):
        CREATE_QRY = '''
            mutation ($created: DateTime!, $digest: String!, $file_name: String!, $file_size: Int!, $produced_by: ID!, $mfd_table: ID!) {
              create_inversion_solution(input: {
                  created: $created
                  md5_digest: $digest
                  file_name: $file_name
                  file_size: $file_size
                  produced_by: $produced_by
                  mfd_table: $mfd_table
                  }
              ) {
              inversion_solution { id }
              }
            }
        '''
        result = self.client.execute(CREATE_QRY,
            variable_values=dict(digest="ABC", file_name='MyInversion.zip', file_size=1000, produced_by="PRODUCER_ID", mfd_table="TABLE_ID"))
        print(result)

        ## >>>>>>>>>>>>>>>
        qry = '''
            mutation ($digest: String!, $file_name: String!, $file_size: Int!) {
              create_file(
                  md5_digest: $digest
                  file_name: $file_name
                  file_size: $file_size

                  ##META##

              ) {
                  ok
                  file_result { id, file_name, file_size, md5_digest, post_url, meta {k v}}
              }
            }'''

        if meta:
            qry = qry.replace("##META##", kvl_to_graphql('meta', meta))

        print(qry)

        filedata = open(filepath, 'rb')
        digest = base64.b64encode(md5(filedata.read()).digest()).decode()
        # print('DIGEST:', digest)

        filedata.seek(0) #important!
        size = len(filedata.read())
        filedata.close()

        variables = dict(digest=digest, file_name=filepath.parts[-1], file_size=size)
        executed = self.run_query(qry, variables)

        print("executed", executed)
        post_url = json.loads(executed['create_file']['file_result']['post_url'])
        return (executed['create_file']['file_result']['id'], post_url)

    def upload_content(self, post_url, filepath):
        print('upload_content **** POST DATA %s' % post_url )
        filedata = open(filepath, 'rb')
        files = {'file': filedata}
        response = requests.post(
            url=self._s3_url,
            data=post_url,
            files=files)
