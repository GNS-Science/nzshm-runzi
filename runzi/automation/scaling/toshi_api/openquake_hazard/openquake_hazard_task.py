
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

class OpenquakeHazardTask(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def get_example_create_variables(self):
        return {"created": "2019-10-01T12:00Z", "model_type": "CRUSTAL", "config_id": "ABCD"}

    def get_example_complete_variables(self):
          return {
          "task_id": "UnVwdHVyZUdlbmVyYXRpb25UYXNrOjA=",
          "hazard_solution_id": "ZZZZZ",
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
            print(values.keys())
            raise ValueError("complete_variables must contain keys: %s" % missing_keys)


    def create_task(self, input_variables, arguments=None, environment=None):
        qry = '''
            mutation create_openquake_hazard_task ($created:DateTime!, $model_type:ModelType!, $config_id: ID!) {
              create_openquake_hazard_task (
                input: {
                  model_type: $model_type
                  created: $created
                  config: $config_id
                  state: STARTED
                  result: UNDEFINED

                  ##ARGUMENTS##

                  ##ENVIRONMENT##
                })
                {
                  openquake_hazard_task {
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
        return executed['create_openquake_hazard_task']['openquake_hazard_task']['id']


    def complete_task(self, input_variables, metrics=None):
        qry = '''
            mutation complete_task (
              $task_id:ID!
              $duration: Float!
              $state:EventState!
              $result:EventResult!
              $hazard_solution_id: ID!
            ){
              update_openquake_hazard_task(input:{
                task_id:$task_id
                duration:$duration
                result:$result
                state:$state
                hazard_solution: $hazard_solution_id

                ##METRICS##

              }) {
                openquake_hazard_task {
                  id
                }
              }
            }
        '''

        if metrics:
            qry = qry.replace("##METRICS##", kvl_to_graphql('metrics', metrics))

        log.debug(f'complete_task() qry: {qry}')

        self.validate_variables(self.get_example_complete_variables(), input_variables)
        executed = self.api.run_query(qry, input_variables)
        return executed['update_openquake_hazard_task']['openquake_hazard_task']['id']
