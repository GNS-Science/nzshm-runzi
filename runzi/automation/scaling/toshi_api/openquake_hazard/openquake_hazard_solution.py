import datetime as dt
import logging

from dateutil.tz import tzutc
from nshm_toshi_client.toshi_client_base import ToshiClientBase, kvl_to_graphql

log = logging.getLogger(__name__)


class OpenquakeHazardSolution(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def create_solution(self, csv_archive_id, hdf5_archive_id, produced_by, predecessors, task_args_id, meta=None):

        qry = '''
            mutation ($created: DateTime!, $csv_archive_id: ID!,
            $hdf5_archive_id: ID!, $produced_by:ID!, $predecessors: [PredecessorInput],
            $task_args_id: ID!){
              create_openquake_hazard_solution(
                  input: {
                      created: $created
                      csv_archive: $csv_archive_id
                      hdf5_archive: $hdf5_archive_id
                      produced_by: $produced_by
                      predecessors: $predecessors
                      task_args: $task_args_id

                      ##META##
                  }
              )
              {
                ok
                openquake_hazard_solution { id }
              }
            }'''
        variables = dict(
            created=dt.datetime.now(tzutc()).isoformat(),
            csv_archive_id=csv_archive_id,
            hdf5_archive_id=hdf5_archive_id,
            produced_by=produced_by,
            predecessors=predecessors,
            task_args_id=task_args_id,
        )

        if meta:
            qry = qry.replace("##META##", kvl_to_graphql('meta', meta))

        executed = self.api.run_query(qry, variables)

        return executed['create_openquake_hazard_solution']['openquake_hazard_solution']['id']

    # def create_archive_file_relation(self, config_id, archive_id, role):
    #     qry = '''
    #     mutation create_file_relation(
    #         $thing_id:ID!
    #         $file_id:ID!
    #         $role:FileRole!) {
    #           create_file_relation(
    #             file_id:$file_id
    #             thing_id:$thing_id
    #             role:$role
    #           )
    #         {
    #           ok
    #         }
    #     }'''
    #     variables = dict(thing_id=config_id, file_id=archive_id, role=role)
    #     executed = self.api.run_query(qry, variables)
    #     return executed['create_file_relation']['ok']

    # def get_solution(self, config_id):

    #     qry = '''
    #     query get_solution($id: ID!) {
    #       node(id:$id) {
    #         __typename
    #         ... on OpenquakeHazardSolution {
    #           created
    #         }
    #       }
    #     }
    #     '''
    #     executed = self.api.run_query(qry, dict(config_id=config_id))
    #     return executed['node']
