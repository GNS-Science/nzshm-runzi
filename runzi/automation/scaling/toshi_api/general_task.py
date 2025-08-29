import copy
import datetime as dt
from enum import Enum

from dateutil.tz import tzutc
from nshm_toshi_client.toshi_client_base import ToshiClientBase


class SubtaskType(Enum):
    RUPTURE_SET = 10
    INVERSION = 20
    HAZARD = 30  # Todo maybe DEPRECATED ?
    REPORT = 40
    SCALE_SOLUTION = 50
    SOLUTION_TO_NRML = 60
    OPENQUAKE_HAZARD = 70
    AGGREGATE_SOLUTION = 80
    TIME_DEPENDENT_SOLUTION = 90


class ModelType(Enum):
    CRUSTAL = 10
    SUBDUCTION = 20
    COMPOSITE = 30


class CreateGeneralTaskArgs(object):

    def __init__(self, title, description, agent_name, created=None):
        self._arguments = dict(
            created=dt.datetime.now(tzutc()).isoformat(),
            agent_name=agent_name,
            title=title,
            description=description,
            argument_lists=[],
            subtask_type='Undefined',
            subtask_count=0,
            model_type='Undefined',
            meta=[],
        )

    def set_argument_list(self, arg_list):
        self._arguments['argument_lists'] = arg_list
        # subtask_count = 1
        # for arg in arg_list:
        #     subtask_count *= len(arg['v'])
        # self._arguments['subtask_count'] = subtask_count
        return self

    def set_meta(self, meta_list):
        self._arguments['meta'] = meta_list
        return self

    def set_subtask_type(self, subtask_type: SubtaskType):
        assert subtask_type.name in [name for name, n in SubtaskType.__members__.items()]
        self._arguments['subtask_type'] = subtask_type.name
        return self

    def set_model_type(self, model_type: ModelType):
        try:
            assert model_type.name in [name for name, n in ModelType.__members__.items()]
        except AssertionError:
            print(f'model_type {model_type} not found in {ModelType}')
            raise
        self._arguments['model_type'] = model_type.name
        return self

    def as_dict(self):
        return copy.copy(self._arguments)


class GeneralTask(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def get_general_task_subtask_files(self, id):
        return self.get_subtask_files(id)

    def get_subtask_files(self, id):
        gt = self.get_general_task_subtasks(id)
        for subtask in gt['children']['edges']:
            sbt = self.get_rgt_files(subtask['node']['child']['id'])
            subtask['node']['child']['files'] = copy.deepcopy(sbt['files'])
            # TESTING
            # break
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
        executed = self.api.run_query(qry, input_variables)
        return executed['node']

    def create_task(self, create_args) -> str:
        '''
        created: DateTime
        When the taskrecord was created
        updated: DateTime
        When task was updated
        agent_name: String
        The name of the person or process responsible for the task
        title: String
        A title always helps
        description: String
        Some description of the task, potentially Markdown
        '''
        assert isinstance(create_args, CreateGeneralTaskArgs)

        qry = '''
            mutation create_gt ($created:DateTime!, $agent_name:String!, $title:String!, $description:String!,
              $argument_lists: [KeyValueListPairInput]!, $subtask_type:TaskSubType!, $subtask_count:Int!,
              $model_type: ModelType!, $meta: [KeyValuePairInput]!) {
              create_general_task (
                input: {
                  created: $created
                  agent_name: $agent_name
                  title: $title
                  description: $description
                  argument_lists: $argument_lists
                  subtask_type: $subtask_type
                  subtask_count:$subtask_count
                  model_type: $model_type
                  meta:$meta
                })
                {
                  general_task {
                    id
                  }
                }
            }
        '''
        print(qry)

        # input_variables = dict(created=created, agent_name=agent_name, title=title, description=description)
        executed = self.api.run_query(qry, create_args.as_dict())
        return executed['create_general_task']['general_task']['id']

    # def get_example_complete_variables(self):
    #       return {"task_id": "UnVwdHVyZUdlbmVyYXRpb25UYXNrOjA=",
    #       "duration": 600,
    #       "result": "SUCCESS",
    #       "state": "DONE",
    #       "subtask_count": 0
    #        }

    # def validate_variables(self, reference, values):
    #     valid_keys = reference.keys()
    #     if not values.keys() == valid_keys:
    #         diffs = set(valid_keys).difference(set(values.keys()))
    #         missing_keys = ", ".join(diffs)
    #         print(valid_keys)
    #         print(values.leys())
    #         raise ValueError("complete_variables must contain keys: %s" % missing_keys)

    def update_subtask_count(self, task_id, subtask_count):
        qry = '''
            mutation update_subtask_count (
              $task_id:ID!
              $subtask_count:Int!
            ){
              update_general_task(input:{
                task_id:$task_id
                subtask_count:$subtask_count
              }) {
                ok
              }
            }

        '''

        print(qry)

        # self.validate_variables(self.get_example_complete_variables(), input_variables)
        executed = self.api.run_query(qry, dict(task_id=task_id, subtask_count=subtask_count))
        return executed['update_general_task']['ok']
