import logging
from enum import Enum

from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql

log = logging.getLogger(__name__)


class HazardTaskType(Enum):
    HAZARD = 10
    DISAGG = 20


class OpenquakeHazardTask(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def get_example_create_variables(self):
        return {"created": "2019-10-01T12:00Z", "model_type": "CRUSTAL"}

    def get_example_complete_variables(self):
        return {"task_id": "UnVwdHVyZUdlbmVyYXRpb25UYXNrOjA=", "duration": 600, "result": "SUCCESS", "state": "DONE"}

    def get_optional_complete_variables(self):
        return {
            "hazard_solution_id": "ZZZZZ",
        }

    def validate_variables(self, reference, optional, values):
        valid_keys = reference.keys()
        optional_keys = optional.keys()
        given_keys = values.keys()
        if not set(given_keys).difference(set(optional_keys)) == set(valid_keys):
            diffs = set(valid_keys).difference(set(values.keys()))
            missing_keys = ", ".join(diffs)
            print(valid_keys)
            print(values.keys())
            raise ValueError("complete_variables must contain keys: %s" % missing_keys)

    def create_task(self, input_variables, arguments=None, environment=None, task_type=HazardTaskType.HAZARD):
        qry = '''
            mutation create_openquake_hazard_task ($created:DateTime!, $model_type:ModelType!) {
              create_openquake_hazard_task (
                input: {
                  model_type: $model_type
                  ###TASK_TYPE###
                  created: $created
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

        qry = qry.replace("###TASK_TYPE###", f"task_type: {task_type.name}")

        log.debug(f'create_task() qry: {qry}')
        self.validate_variables(self.get_example_create_variables(), {}, input_variables)

        executed = self.api.run_query(qry, input_variables)
        return executed['create_openquake_hazard_task']['openquake_hazard_task']['id']

    def complete_task(self, input_variables, metrics=None):
        qry = '''
            mutation complete_task (
              $task_id:ID!
              $duration: Float!
              $state:EventState!
              $result:EventResult!
              ##HAZARD_ID1##
            ){
              update_openquake_hazard_task(input:{
                task_id:$task_id
                duration:$duration
                result:$result
                state:$state
                ##HAZARD_ID2##

                ##METRICS##

              }) {
                openquake_hazard_task {
                  id
                }
              }
            }
        '''

        if input_variables['hazard_solution_id']:
            qry = qry.replace("##HAZARD_ID1##", "$hazard_solution_id: ID!")
            qry = qry.replace("##HAZARD_ID2##", "hazard_solution: $hazard_solution_id")

        if metrics:
            qry = qry.replace("##METRICS##", kvl_to_graphql('metrics', metrics))

        log.debug(f'complete_task() qry: {qry}')

        self.validate_variables(
            self.get_example_complete_variables(), self.get_optional_complete_variables(), input_variables
        )
        executed = self.api.run_query(qry, input_variables)
        return executed['update_openquake_hazard_task']['openquake_hazard_task']['id']
