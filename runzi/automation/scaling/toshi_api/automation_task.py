import datetime as dt
from dateutil.tz import tzutc
from hashlib import md5
from pathlib import PurePath

import base64
# import copy
import json
import requests

from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql

import logging
log = logging.getLogger(__name__)
# log.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)

class AutomationTask(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def create_task(self, input_variables, arguments=None, environment=None):
        qry = '''
            mutation create_task ($created:DateTime!, $task_type:TaskSubType!, $model_type:ModelType!) {
              create_automation_task (
                input: {
                  task_type: $task_type
                  model_type: $model_type
                  created: $created
                  state:STARTED
                  result:UNDEFINED

                  ##ARGUMENTS##

                  ##ENVIRONMENT##
                })
                {
                  task_result {
                    id
                    }
                }
            }
        '''

        if arguments:
            qry = qry.replace("##ARGUMENTS##", kvl_to_graphql('arguments', arguments))
        if environment:
            qry = qry.replace("##ENVIRONMENT##", kvl_to_graphql('environment', environment))

        log.debug(f'create_task() qry: {qry}')
        self.validate_variables(self.get_example_create_variables(), input_variables)

        executed = self.api.run_query(qry, input_variables)
        return executed['create_automation_task']['task_result']['id']

    def upload_file(self, filepath, meta=None):
        filepath = PurePath(filepath)
        file_id, post_url = self.api.file.create_file(filepath, meta)
        self.api.file.upload_content(post_url, filepath)
        return file_id

    def link_task_file(self, task_id, file_id, task_role):
        return self.api.task_file.create_task_file(task_id, file_id, task_role)

    def upload_task_file(self, task_id, filepath, task_role, meta=None):
        filepath = PurePath(filepath)
        file_id = self.upload_file(filepath, meta)
        #link file to task in role
        return self.link_task_file(task_id, file_id, task_role)

    def get_example_create_variables(self):
        return {"created": "2019-10-01T12:00Z", "task_type": "INVERSION", "model_type": "CRUSTAL"}

    def get_example_complete_variables(self):
          return {"task_id": "UnVwdHVyZUdlbmVyYXRpb25UYXNrOjA=",
          "duration": 600,
          "result": "SUCCESS",
          "state": "DONE"
           }

    def validate_variables(self, reference, values):
        valid_keys = reference.keys()
        if not values.keys() == valid_keys:
            diffs = set(valid_keys).difference(set(values.keys()))
            missing_keys = ", ".join(diffs)
            print(valid_keys)
            print(values.leys())
            raise ValueError("complete_variables must contain keys: %s" % missing_keys)

    def complete_task(self, input_variables, metrics=None):
        qry = '''
            mutation complete_task (
              $task_id:ID!
              $duration: Float!
              $state:EventState!
              $result:EventResult!
            ){
              update_automation_task(input:{
                task_id:$task_id
                duration:$duration
                result:$result
                state:$state

                ##METRICS##

              }) {
                task_result {
                  id
                  metrics {k v}
                }
              }
            }

        '''

        if metrics:
            qry = qry.replace("##METRICS##", kvl_to_graphql('metrics', metrics))

        log.debug(f'complete_task() qry: {qry}')

        self.validate_variables(self.get_example_complete_variables(), input_variables)
        executed = self.api.run_query(qry, input_variables)
        return executed['update_automation_task']['task_result']['id']


# class CreateAutomationArgs(object):

#     def __init__(self, title, description, agent_name, created=None):
#         self._arguments = dict(
#           created = dt.datetime.now(tzutc()).isoformat(),
#           agent_name = agent_name,
#           title = title,
#           description = description,
#           argument_lists = [],
#           subtask_type = 'Undefined',
#           subtask_count = 0,
#           model_type = 'Undefined',
#           meta = []
#         )

#     def set_argument_list(self, arg_list):
#         self._arguments['argument_lists'] = arg_list
#         subtask_count = 1
#         for arg in arg_list:
#             subtask_count *= len(arg['v'])
#         self._arguments['subtask_count'] = subtask_count
#         return self

#     def set_meta(self, meta_list):
#         self._arguments['meta'] = meta_list
#         return self

#     def set_subtask_type(self, subtask_type):
#         assert subtask_type in ['RUPTURE_SETS', 'INVERSIONS', 'HAZARD']
#         self._arguments['subtask_type'] = subtask_type
#         return self

#     def set_model_type(self, model_type):
#         assert model_type in ['CRUSTAL', 'SUBDUCTION']
#         self._arguments['model_type'] = model_type
#         return self

#     def as_dict(self):
#         return copy.copy(self._arguments)
