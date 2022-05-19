from runzi.automation.scaling.toshi_api.general_task import ModelType

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
    
    if typename == 'InversionSolution':
        qry = '''
        query invsoln ($id:ID!) {
            node (id: $id) {
                ... on InversionSolution {
                    produced_by_id
                }
            }
        }'''

        input_variables = dict(id=id)
        auto_id = toshi_api.run_query(qry, input_variables)['node']['produced_by_id']
    elif typename == 'ScaledInversionSolution':
        qry = '''
            query scaledinvsoln ($id:ID!) {
                node (id: $id) {
                    ... on ScaledInversionSolution {
                    produced_by { id }
                    }
                }
            }'''
        input_variables = dict(id=id)
        auto_id = toshi_api.run_query(qry, input_variables)['node']['produced_by']['id']
    else:
        raise Exception(f'typename must be InversionSolution or ScaledInversionSolution, {typename} given')
    
    qry = '''
    query autotask ($id:ID!) {
        node (id: $id) {
           ... on AutomationTask{
                model_type
                }
            }
    }'''
    input_variables = dict(id=auto_id)
    model_type_str = toshi_api.run_query(qry, input_variables)['node']['model_type']

    return ModelType[model_type_str]

    
def get_model_type(ids: list, toshi_api):

    model_type = _get_model_type(ids[0],toshi_api)
    # check that all models types are the same
    for id in ids:
        mt = _get_model_type(id,toshi_api)
        assert mt is model_type, 'not all model types in source id list are the same'
    
    return model_type