#!oq_build_sources.py

import itertools
import logging
from pathlib import Path

import zipfile
from lxml import etree
from lxml.builder import ElementMaker # lxml only !
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

log = logging.getLogger(__name__)

def get_ltb(group):
    for gk, gv in group.items():
        yield list(gv.items())

def get_logic_tree_file_ids(ltb_groups):
    ids = set()
    for group in ltb_groups: #List
        for sources in get_ltb(group):
            for source in sources:
                ids.add( source )
    return list(ids)

def get_logic_tree_branches(ltb_groups):
    for group in ltb_groups: #List
        for ltb in itertools.product(*get_ltb(group)):
            yield ltb

class SourceModelLoader():

    def __init__(self, api_url, api_key, s3_url):
        headers={"x-api-key":api_key}
        self._toshi_api = ToshiApi(api_url, s3_url, None, with_schema_validation=True, headers=headers)

    def unpack_sources(self, logic_tree_branch_permutations, source_path):
        """download and extract the sources"""

        sources = dict()

        # ltbs = [x for x in get_logic_tree_file_ids(logic_tree_branch_permutations)]

        # print(ltbs)
        # print(len(ltbs))

        for src_name, nrml_id in get_logic_tree_file_ids(logic_tree_branch_permutations):
            if nrml_id in sources.keys():
                continue

            log.info(f"get src : {src_name} {nrml_id}")

            gen = get_output_file_id(self._toshi_api, nrml_id)

            source_nrml = download_files(self._toshi_api, gen, str(WORK_PATH), overwrite=False)
            log.info(f"source_nrml: {source_nrml}")

            with zipfile.ZipFile(source_nrml[nrml_id]['filepath'], 'r') as zip_ref:
                zip_ref.extractall(source_path)
                sources[nrml_id] = {'source_name': src_name, 'sources' : zip_ref.namelist()}
        return sources


def build_sources_xml(logic_tree_branches, source_file_mapping):

    weight = 1/len(logic_tree_branches)

    E = ElementMaker(namespace="http://openquake.org/xmlns/nrml/0.5",
                      nsmap={"gml" : "http://www.opengis.net/gml", None:"http://openquake.org/xmlns/nrml/0.5"})
    NRML = E.nrml
    LT = E.logicTree
    LTBS = E.logicTreeBranchSet
    LTBL = E.logicTreeBranchingLevel
    LTB = E.logicTreeBranch
    UM = E.uncertaintyModel
    UW = E.uncertaintyWeight

    ltbs = LTBS(uncertaintyType="sourceModel", branchSetID="BS-NONCE1")

    for branch in logic_tree_branches:
            files = ""
            branch_name = ", ".join([x[0] for x in branch])
            for source_tuple in branch:
                #print(source_tuple)
                name, src_id = source_tuple
                files += "\t".join(source_file_mapping[src_id]['sources']) + "\t"
            ltb = LTB( UM(files), UW(str(weight)), branchID=branch_name)
            ltbs.append(ltb)

    nrml = NRML( LT( LTBL( ltbs, branchingLevelID="1" ), logicTreeID = "Combined"))
    return etree.tostring(nrml, pretty_print=True).decode()



if __name__ == "__main__":
    from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)

    permutations = [
        {
            "CR": {
                "CR_N2.3_b0.807_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MA==",
                "CR_N8.0_b1.115_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Nw==",
                "CR_N2.3_b0.807_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OQ==",
                "CR_N3.7_b0.929_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MQ==",
                "CR_N3.7_b0.929_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Mw==",
                "CR_N8.0_b1.115_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4NQ=="
                },
            "HK": {
                "HTC_b1.112_N22.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NA==",
                "HTC_b0.97_N11.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Ng==",
                "HTC_b1.3_N49.4_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3MQ==",
                "HTL_b1.112_N22.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3MA==",
                "HTL_b0.97_N11.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Mw==",
                "HTL_b1.3_N49.4_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Mg=="
            },
            # "BG": {
            #     "floor_addtot346ave": "FILL IN THE BLANK"
            # },
            "PY": {
                "P_b0.75, N3.4_C3.9_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="
            }
        },
        {
            "CR": {
                "CR_N8.0_b1.115_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OA==",
                "CR_N2.3_b0.807_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Mg==",
                "CR_N3.7_b0.929_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4NA=="
                },
            "HK": {
                "HTC_b1.112_N22.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Nw==",
                "HTC_b1.3_N49.4_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NQ==",
                "HTC_b0.97_N11.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OA==",
                "HTL_b1.112_N22.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OQ==",
                "HTL_b1.3_N49.4_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3NQ==",
                "HTL_b0.97_N11.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3NA=="
            },
            # "BG": {
            #     #"floor_addtot346ave": "FILL IN THE BLANK"
            # },
            "PY": {
                "P_b0.75_N3.4_C3.9_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="
            }
        }
    ]
    logging.basicConfig(level=logging.INFO)
    sources_folder = Path(WORK_PATH, 'sources')
    source_file_mapping = SourceModelLoader(API_URL, API_KEY, S3_URL).unpack_sources(permutations, sources_folder)
    # print(source_file_mapping)

    ltbs = [ltb for ltb in get_logic_tree_branches(permutations)]

    print("LTB:", len(ltbs), ltbs[0])

    nrml = build_sources_xml(ltbs, source_file_mapping)
    print(nrml)


    # task_args = {
    #     "logic_tree_permutations" : [
    #         {
    #             "CR": {
    #                 "CR_N7.8_b_1.111_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0NA==",
    #                 "CR_N7.8_b_1.111_s2": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0NQ==",
    #                 "CR_N3.5_b0.913_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Ng==",
    #                 #"CR_N3.5_b0.913_s2": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Nw=="
    #                 },
    #             "HK": {
    #                 "HK_N25.6_b0.942_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OA==",
    #                 "HK_N25.6_b1.009_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OQ==",
    #                 #"HK_N25.6_b1.009_s12": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM1MA=="
    #             },
    #             "BG": {
    #                 "bgA": "RmlsZToxMDE4MDI="
    #             },
    #             "PY": {
    #                 "PY_N": "RmlsZToxMDE4MDA="
    #             }
    #         },
    #         #MORE of these ....
    #     ]
    # }

    #this is produced by
    # source_file_mapping = {
    #     "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0NA==" :
    #     {
    #         'source_name': 'CR_N7.8_b_1.111_s1',
    #         'sources' : ['path/to/fileA', 'path/to/FileA1']
    #     },
    #     "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0NQ==" :
    #     {
    #         'source_name': 'CR_N7.8_b_1.111_s1',
    #         'sources' : ['path/to/fileB', 'path/to/FileB1']
    #     },
    #     "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Ng==" :
    #     {
    #         'source_name': 'CR_N7.8_b_1.111_s1',
    #         'sources' : ['path/to/fileC', 'path/to/FileC1']
    #     },
    #     "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OA==" :
    #     {
    #         'source_name': 'CR_N7.8_b_1.111_s1',
    #         'sources' : ['path/to/fileD', 'path/to/FileD1']
    #     },
    #     "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0OQ==" :
    #     {
    #         'source_name': 'CR_N7.8_b_1.111_s2',
    #         'sources' : ['path/to/fileE', 'path/to/FileE1']
    #     },
    #     "RmlsZToxMDE4MDI=" :
    #     {
    #         'source_name': 'BG',
    #         'sources' : ['path/to/fileBG']
    #     },
    #     "RmlsZToxMDE4MDA=" :
    #     {
    #         'source_name': 'PY',
    #         'sources' : ['path/to/filePY']
    #     }

    # }

    # id_list = get_logic_tree_file_ids(task_args['logic_tree_permutations'])
    # #print("ID lists:", list(id_list))
    # #TODO build a map whlie downloading the files

