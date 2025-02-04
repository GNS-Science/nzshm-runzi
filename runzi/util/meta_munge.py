#! meta_munge.py

import hashlib
import json

from jsonpath_ng import jsonpath, parse

"""
merge the meta data from openquake hazard job with meta from ToshiAPI

Temporary solution until the job meta is saved to the API as part of normal  hazard execution

"""

# def simple_meta(meta_item):
#     simple = {meta_item['solution_id']}
#     return simple

# for meta_item in meta[:1]:
#     print(f"simple: {simple_meta(meta_item)}")
#     print(meta_item)

# """
# # A robust parser, not just a regex. (Makes powerful extensions possible; see below)
# >>> jsonpath_expr = parse('foo[*].baz')

# # Extracting values is easy
# >>> [match.value for match in jsonpath_expr.find({'foo': [{'baz': 1}, {'baz': 2}]})]
# [1, 2]
# """

# print()
# print()
# print()

# jp_expr = parse('data.node.children.edges[*].node.child')
# m2 = [match for match in jp2_expr.find(m)]


def get_kv_meta(kv_meta):
    # jp_expr = parse('[*].k.`parent`')
    res = dict()
    sub_b_and_n = {}
    for kvp in kv_meta:
        # "k": "mfd_mag_gt_5",
        #                       "v": "25.6"
        #                     },
        #                     {
        #                       "k": "mfd_b_value",
        #                       "v": "1.009"
        if kvp['k'] in ['scale', 'b_and_n', 'config_type']:
            res[kvp['k']] = kvp['v']
        # Subduction
        if kvp['k'] in ['mfd_mag_gt_5', 'mfd_b_value']:
            # res[kvp['k']] = kvp['v']
            sub_b_and_n[kvp['k']] = kvp['v']

    if sub_b_and_n:
        res['b_and_n'] = str(dict(b=float(sub_b_and_n['mfd_b_value']), N=float(sub_b_and_n['mfd_mag_gt_5'])))
    return res


def get_nrml_nodes(meta):
    jp_expr = parse('data.node.children.edges[*].node.child')  # .__typename["AutomationTask"]
    jp2_expr = parse('files.edges[*].node.file')
    # AutomationTask
    for match0 in jp_expr.find(meta):
        # print(match0.id_pseudopath)
        # Files
        res = dict(solution=dict())
        for match1 in jp2_expr.find(match0):
            # print(f'{match1.id_pseudopath}')
            if match1.value['__typename'] == "InversionSolutionNrml":
                res['nrml_id'] = match1.value['id']
                # res['nrml_src_id'] = match1.value['source_solution']['id']
            elif match1.value['__typename'] == "InversionSolution":
                # res['solution']['id'] = match1.value['id']
                res['solution']['__typename'] = match1.value['__typename']
                res['solution']['solution_meta'] = get_kv_meta(match1.value['meta'])
            elif match1.value['__typename'] == "ScaledInversionSolution":
                # res['solution']['id'] = match1.value['id']
                res['solution']['__typename'] = match1.value['__typename']
                res['solution']['scaling_meta'] = get_kv_meta(match1.value['meta'])
                res['solution']['solution_meta'] = get_kv_meta(match1.value["source_solution"]['meta'])
        yield res


def get_nrml_by_id(nrmls, id):
    for n in nrmls:
        if n['nrml_id'] == id:
            return n


def shaped_meta(nrmls, meta_item):
    res = dict()
    ta = meta_item["meta"]["task_arguments"]
    config_hash = hashlib.md5(ta['config_file'].encode('utf-8')).hexdigest()
    res['nrml_id'] = meta_item['solution_id']
    res['config_hash'] = config_hash
    res['path'] = f"{config_hash[-8:]}/{meta_item['solution_id']}"
    res['task_arguments'] = ta
    res['detail'] = get_nrml_by_id(nrmls, meta_item['solution_id'])
    return res


if __name__ == "__main__":

    task_json = "meta-pass1-metadata.json"  # the oq_hazard_task function wirtes this file
    m1 = "meta-R2VuZXJhbFRhc2s6MTAwMjA2.json"  # produced manually using the API query below
    m2 = "meta-api-R2VuZXJhbFRhc2s6MTAwMTk2.json"  # ditto

    task_meta = json.load(open(task_json, 'r'))
    api_meta1 = json.load(open(m1))
    api_meta2 = json.load(open(m2))

    # the nrml meta from each API resul
    nrmls = [i for i in get_nrml_nodes(api_meta1)]
    nrmls += [i for i in get_nrml_nodes(api_meta2)]

    res = dict()
    for mmm in task_meta:
        shaped = shaped_meta(nrmls, mmm)
        res[shaped['path']] = shaped

    # write out the combined metadata which feeds into jupyter hazard reports
    with open("meta.json", 'w') as fout:
        fout.write(json.dumps(res, indent=4))

    print("Done!")

    QRY = """
query conversion_gt {
  #node(id:"R2VuZXJhbFRhc2s6MTAwMTQ2") {
  #node(id:"R2VuZXJhbFRhc2s6MTAwMTk2") {
  node(id:"R2VuZXJhbFRhc2s6MTAwMjA2") {

  ... on GeneralTask {
    id
    title
    description
    subtask_count
    subtask_type
    model_type
    agent_name
    argument_lists{ k v }

    children {
      edges {
        node {
          child {
            __typename
            ... on AutomationTask {
              id
              state
              duration
              arguments {
                k
                v
              }
              files {total_count
                edges {
                    node {
                    role
                    file {
                    __typename
                      ... on InversionSolutionNrml {
                        id
                        created
                        file_name # link to file system
                        # file_size
                        # file_url
                        source_solution { id }
                      }
                      
                      ... on ScaledInversionSolution {
                        file_name
                        created
                        meta {k v}
                        source_solution {
                          id #link to TOSHI
                          meta {k v}
                          }
                      }                      
                      
                      ... on InversionSolution {
                        id
                        file_name
                        meta {k v}
                        created
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
}

"""
