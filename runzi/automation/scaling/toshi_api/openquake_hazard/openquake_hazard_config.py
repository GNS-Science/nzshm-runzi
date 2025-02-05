import logging
from datetime import datetime as dt

from dateutil.tz import tzutc
from nshm_toshi_client.toshi_client_base import ToshiClientBase

log = logging.getLogger(__name__)


class OpenquakeHazardConfig(object):

    def __init__(self, api):
        self.api = api
        assert isinstance(api, ToshiClientBase)

    def create_config(self, source_models, archive_id):
        qry = '''
            mutation ($created: DateTime!, $source_models: [ID]!, $archive_id: ID!) {
              create_openquake_hazard_config(
                  input: {
                      created: $created
                      source_models: $source_models
                      template_archive: $archive_id
                  }
              )
              {
                ok
                config { id, created, source_models {
                  ... on Node { id } }
                }
              }
            }
        '''
        created = dt.now(tzutc()).isoformat()
        variables = dict(source_models=source_models, archive_id=archive_id, created=created)

        executed = self.api.run_query(qry, variables)

        return executed['create_openquake_hazard_config']['config']['id']

    def create_archive_file_relation(self, config_id, archive_id, role):
        qry = '''
        mutation create_file_relation(
            $thing_id:ID!
            $file_id:ID!
            $role:FileRole!) {
              create_file_relation(
                file_id:$file_id
                thing_id:$thing_id
                role:$role
              )
            {
              ok
            }
        }'''
        variables = dict(thing_id=config_id, file_id=archive_id, role=role)
        executed = self.api.run_query(qry, variables)
        return executed['create_file_relation']['ok']

    def get_config(self, config_id):

        qry = '''
        query get_hazard_config ($config_id: ID!) {
          node(id:$config_id) {
            __typename
            ... on OpenquakeHazardConfig{
              created
              source_models { id }
              template_archive {
                id
                file_name
                file_url
                file_size
                md5_digest
                meta {k v}
              }
            }
          }
        }
        '''
        executed = self.api.run_query(qry, dict(config_id=config_id))
        return executed['node']
