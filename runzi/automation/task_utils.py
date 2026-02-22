from runzi.automation.toshi_api.general_task import ModelType


def _get_model_type(id, toshi_api):
    # get the type
    qry = '''
    query soln1 ($id:ID!) {
         node (id: $id) {
        __typename
        }
    }'''
    input_variables = dict(id=id)
    typename = toshi_api.run_query(qry, input_variables)['node']['__typename']

    qry = '''
    query invsoln ($id:ID!) {
        node (id: $id) {
            ... on TYPENAME {
                produced_by { ... on Node{id} }
            }
        }
    }'''
    qry = qry.replace('TYPENAME', typename)
    input_variables = dict(id=id)
    auto_id = toshi_api.run_query(qry, input_variables)['node']['produced_by']['id']

    qry = '''
    query autotask ($id:ID!) {
        node (id: $id) {
           ... on ###AUTOTASK###{
                model_type
                }
            }
    }'''
    autotask_type = "RuptureGenerationTask" if typename == "RuptureSet" else "AutomationTask"
    qry = qry.replace("###AUTOTASK###", autotask_type)
    input_variables = dict(id=auto_id)
    model_type_str = toshi_api.run_query(qry, input_variables)['node']['model_type']

    return ModelType[model_type_str]


def get_model_type(ids: list, toshi_api):

    model_type = _get_model_type(ids[0], toshi_api)
    # check that all models types are the same
    for id in ids:
        mt = _get_model_type(id, toshi_api)
        if mt is not model_type:
            raise ValueError('not all model types in source id list are the same')

    return model_type
