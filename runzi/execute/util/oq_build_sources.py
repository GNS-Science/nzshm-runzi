#!oq_build_sources.py

import itertools
import logging
from pathlib import Path
import collections

import zipfile
from lxml import etree
from lxml.builder import ElementMaker # lxml only !
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id
from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH)

log = logging.getLogger(__name__)


# def get_ltb(group):
#     """old dict-kets style config"""
#     for gk, gv in group.items():
#         yield list(gv.items())

# Using a named tuple make the data much easier to work with...
# this is where we change source_model to use toshi_id
LogicTreeBranch = collections.namedtuple('LogicTreeBranch', 'tag toshi_id weight')


def get_logic_tree_file_ids(ltb_groups):
    ids = set()
    for group in ltb_groups: #List
        for sources in get_ltb(group):
            for source in sources:
                ids.add( (source.tag, source.toshi_id ))
    return list(ids)

def get_ltb(group):
    """NEW object-syle config"""
    for obj in group['permute']:
        yield [LogicTreeBranch(tag=source['tag'], toshi_id=source['toshi_id'], weight=source['weight']) for source in obj['members']]

def get_logic_tree_branches(ltb_groups):
    for group in ltb_groups: #List
        for ltb in itertools.product(*get_ltb(group)):
            yield ltb

class SourceModelLoader():

    def __init__(self):
        headers={"x-api-key":API_KEY}
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    def unpack_sources(self, logic_tree_branch_permutations, source_path):
        """download and extract the sources"""

        sources = dict()

        # ltbs = [x for x in get_logic_tree_file_ids(logic_tree_branch_permutations)]

        # print(ltbs)
        # print(len(ltbs))
        print(logic_tree_branch_permutations)

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

    #weight = 1/len(logic_tree_branches)
    total_branch_weight = 0
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
            branch_name = "|".join([ltb.toshi_id for ltb in branch])
            branch_weight = 1.0
            for ltb in branch:
                #print(ltb)
                #name, src_id, wt = source_tuple
                files += "\t".join(source_file_mapping[ltb.toshi_id]['sources']) + "\t"
                branch_weight *= ltb.weight
            #branch_weight = round(branch_weight, 10)
            total_branch_weight += branch_weight
            ltb = LTB( UM(files), UW(str(branch_weight)), branchID=branch_name)
            ltbs.append(ltb)

    print(f'total_branch_weight: {total_branch_weight}')
    assert round(total_branch_weight, 8) == 1.0

    nrml = NRML( LT( LTBL( ltbs, branchingLevelID="1" ), logicTreeID = "Combined"))
    return etree.tostring(nrml, pretty_print=True).decode()



if __name__ == "__main__":
    from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)

    # permutations = [
    #     {
    #         "CR": {
    #             "CR_N2.3_b0.807_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MA==",
    #             "CR_N8.0_b1.115_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Nw==",
    #             "CR_N2.3_b0.807_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OQ==",
    #             "CR_N3.7_b0.929_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MQ==",
    #             "CR_N3.7_b0.929_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Mw==",
    #             "CR_N8.0_b1.115_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4NQ=="
    #             },
    #         "HK": {
    #             "HTC_b1.112_N22.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NA==",
    #             "HTC_b0.97_N11.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Ng==",
    #             "HTC_b1.3_N49.4_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3MQ==",
    #             "HTL_b1.112_N22.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3MA==",
    #             "HTL_b0.97_N11.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Mw==",
    #             "HTL_b1.3_N49.4_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Mg=="
    #         },
    #         "BG": {
    #             "BG_floor_addtot346ave": "RmlsZToxMDIyMzA="
    #         },
    #         "PY": {
    #             "PY_b0.75_N3.4_C3.9_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="
    #         }
    #     },
    #     {
    #         "CR": {
    #             "CR_N8.0_b1.115_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OA==",
    #             "CR_N2.3_b0.807_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Mg==",
    #             "CR_N3.7_b0.929_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4NA=="
    #             },
    #         "HK": {
    #             "HTC_b1.112_N22.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Nw==",
    #             "HTC_b1.3_N49.4_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NQ==",
    #             "HTC_b0.97_N11.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OA==",
    #             "HTL_b1.112_N22.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OQ==",
    #             "HTL_b1.3_N49.4_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3NQ==",
    #             "HTL_b0.97_N11.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3NA=="
    #         },
    #         "BG": {
    #             "BG_floor_addtot346ave": "RmlsZToxMDIyMzA="
    #         },
    #         "PY": {
    #             "PY_b0.75_N3.4_C3.9_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="
    #         }
    #     }
    # ]

    # #SLT001
    # permutations = [
    #     {
    #         "tag": "core model", "weight": 1.0,
    #         "permute" : [
    #             {
    #                 "group": "HIK",
    #                 "members" : [
    #                     {"tag": "b0.97_N11.6_C4.0_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Ng=="}
    #                 ]
    #             }
    #         ]
    #     }
    # ]


    # #SLT002
    # permutations = [
    # {
    #     "tag": "core model", "weight": 0.5,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.0_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Ng=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "C = 4.1", "weight": 0.5,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.1_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OA=="}
    #             ]
    #         }
    #     ]
    # }

    # ]


    # #SLT003
    # permutations = [

    # {
    #     "tag": "core model", "weight": 0.166,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.0_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Ng=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "core scaled down", "weight": 0.166,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.0_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Nw=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "core scaled up", "weight": 0.166,
    #     "permute" : [

    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.0_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5OA=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112", "weight": 0.166,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NA=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112 scaled down", "weight": 0.166,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Ng=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112 scaled up", "weight": 0.17,
    #     "permute" : [

    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5OQ=="}
    #             ]
    #         }
    #     ]
    # }
    # ]

    # #SLT004b
    # permutations = [

    # {
    #     "tag": "core model", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.0_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Ng=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "core scaled down", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.0_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Nw=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "core scaled up", "weight": 0.0833,
    #     "permute" : [

    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.0_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5OA=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NA=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112 scaled down", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Ng=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112 scaled up", "weight": 0.0833,
    #     "permute" : [

    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5OQ=="}
    #             ]
    #         }
    #     ]
    # },


    # {
    #     "tag": "core model, C = 4.1", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.1_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OA=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "core scaled down, C = 4.1", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.1_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4OQ=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "core scaled up, C = 4.1", "weight": 0.0833,
    #     "permute" : [

    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b0.97_N11.6_C4.1_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwMA=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112, C = 4.1", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4.1_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Nw=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112 scaled down, C = 4.1", "weight": 0.0833,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4.1_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5MA=="}
    #             ]
    #         }
    #     ]
    # },

    # {
    #     "tag": "b = 1.112 scaled up, C = 4.1", "weight": 0.0837,
    #     "permute" : [

    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "b1.112_N22.6_C4.1_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwMw=="}
    #             ]
    #         }
    #     ]
    # }

    # ]


    #BIG
    # permutations = [
    #     {
    #         "CR": {
    #             "CR_N8.0_b1.115_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OA==",
    #             "CR_N2.3_b0.807_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MA==",
    #             "CR_N8.0_b1.115_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Nw==",
    #             "CR_N2.3_b0.807_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OQ==",
    #             "CR_N3.7_b0.929_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MQ==",
    #             "CR_N3.7_b0.929_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Mw==",
    #             "CR_N2.3_b0.807_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Mg==",
    #             "CR_N3.7_b0.929_C4.3_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4NA==",
    #             "CR_N8.0_b1.115_C4.2_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4NQ=="
    #             },
    #         "HK": {
    #             "HTC_b1.112_N22.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NA==",
    #             "HTC_b1.112_N22.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Nw==",
    #             "HTC_b1.3_N49.4_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2NQ==",
    #             "HTC_b0.97_N11.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2Ng==",
    #             "HTC_b0.97_N11.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OA==",
    #             "HTC_b1.3_N49.4_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3MQ==",
    #             "HTL_b1.112_N22.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE2OQ==",
    #             "HTL_b1.112_N22.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3MA==",
    #             "HTL_b0.97_N11.6_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Mw==",
    #             "HTL_b1.3_N49.4_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3NQ==",
    #             "HTL_b1.3_N49.4_C4_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Mg==",
    #             "HTL_b0.97_N11.6_C4.1_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3NA=="
    #         },
    #         "BG": {
    #             "floor_addtot346ave": "RmlsZToxMDIyMzA="
    #         },
    #         "PY": {
    #             "P_b0.75_N3.4_C3.9_s1": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="
    #         }
    #     },
    #     {
    #         "CR": {
    #             "CR_N8.0_b1.115_C4.3_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMg==",
    #             "CR_N8.0_b1.115_C4.1_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNQ==",
    #             "CR_N2.3_b0.807_C4.2_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNg==",
    #             "CR_N2.3_b0.807_C4.1_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMw==",
    #             "CR_N3.7_b0.929_C4.1_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNA==",
    #             "CR_N3.7_b0.929_C4.2_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNw==",
    #             "CR_N2.3_b0.807_C4.3_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxOQ==",
    #             "CR_N8.0_b1.115_C4.2_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMA==",
    #             "CR_N3.7_b0.929_C4.3_s0.51": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMw=="
    #             },
    #         "HK": {
    #             "HTC_b1.112_N22.6_C4_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Ng==",
    #             "HTC_b1.3_N49.4_C4.1_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4OA==",
    #             "HTC_b1.112_N22.6_C4.1_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5MA==",
    #             "HTC_b0.97_N11.6_C4_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4Nw==",
    #             "HTC_b0.97_N11.6_C4.1_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4OQ==",
    #             "HTL_b1.112_N22.6_C4.1_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5MQ==",
    #             "HTC_b1.3_N49.4_C4_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5Mg==",
    #             "HTL_b1.112_N22.6_C4_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5NQ==",
    #             "HTL_b0.97_N11.6_C4_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5Ng==",
    #             "HTL_b1.3_N49.4_C4_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5Mw==",
    #             "HTL_b1.3_N49.4_C4.1_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5NA==",
    #             "HTL_b0.97_N11.6_C4.1_s0.54": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5Nw=="
    #         },
    #         "BG": {
    #             "floor_addtot346ave": "RmlsZToxMDIyMzA="
    #         },
    #         "PY": {
    #             "P_b0.75_N3.4_C3.9_s0.61": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMA=="
    #         }
    #     },
    #     {
    #         "CR": {
    #             "CR_N2.3_b0.807_C4.2_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxOA==",
    #             "CR_N8.0_b1.115_C4.3_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMQ==",
    #             "CR_N8.0_b1.115_C4.1_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMg==",
    #             "CR_N3.7_b0.929_C4.2_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNA==",
    #             "CR_N2.3_b0.807_C4.1_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNg==",
    #             "CR_N3.7_b0.929_C4.1_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyOA==",
    #             "CR_N3.7_b0.929_C4.3_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNQ==",
    #             "CR_N2.3_b0.807_C4.3_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNw==",
    #             "CR_N8.0_b1.115_C4.2_s1.62": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyOQ=="
    #             },
    #         "HK": {
    #             "HTC_b1.112_N22.6_C4_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5OQ==",
    #             "HTC_b1.3_N49.4_C4.1_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwMQ==",
    #             "HTC_b1.112_N22.6_C4.1_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwMw==",
    #             "HTC_b0.97_N11.6_C4_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE5OA==",
    #             "HTC_b0.97_N11.6_C4.1_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwMA==",
    #             "HTL_b1.112_N22.6_C4.1_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwMg==",
    #             "HTC_b1.3_N49.4_C4_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwNA==",
    #             "HTL_b1.112_N22.6_C4_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwNw==",
    #             "HTL_b0.97_N11.6_C4_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwOA==",
    #             "HTL_b1.3_N49.4_C4_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwNQ==",
    #             "HTL_b1.3_N49.4_C4.1_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwNg==",
    #             "HTL_b0.97_N11.6_C4.1_s1.43": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIwOQ=="
    #         },
    #         "BG": {
    #             "floor_addtot346ave": "RmlsZToxMDIyMzA="
    #         },
    #         "PY": {
    #             "P_b0.75_N3.4_C3.9_s1.34": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMQ=="
    #         }
    #     }
    # ]


    #27_TAG_CONFIG
    # permutations = [
    #     {
    #         "tag": "all rate combinations", "weight": 1.0,
    #         "permute" : [
    #             {   "group": "HIK",
    #                 "members" : [
    #                     {"tag": "HTC_b0.957_N16.5_C4.1_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk0OQ=="},
    #                     {"tag": "HTC_b1.078_N22.8_C4.1_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MA=="},
    #                     {"tag": "HTL_b0.957_N16.5_C4.1_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MQ=="},
    #                     {"tag": "HTL_b1.078_N22.8_C4.1_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mg=="},
    #                     {"tag": "HTC_b0.957_N16.5_C4.1_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mw=="},
    #                     {"tag": "HTC_b0.957_N16.5_C4.1_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NA=="},
    #                     {"tag": "HTC_b1.078_N22.8_C4.1_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NQ=="},
    #                     {"tag": "HTC_b1.078_N22.8_C4.1_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Ng=="},
    #                     {"tag": "HTL_b0.957_N16.5_C4.1_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Nw=="},
    #                     {"tag": "HTL_b0.957_N16.5_C4.1_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OA=="},
    #                     {"tag": "HTL_b1.078_N22.8_C4.1_s0.54", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OQ=="},
    #                     {"tag": "HTL_b1.078_N22.8_C4.1_s1.43", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk2MA=="}
    #                 ]
    #             },
    #             {   "group": "PUY",
    #                 "members" : [
    #                     {"tag": "P_b0.75_N3.4_C3.9_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="}
    #                 ]
    #             },
    #             {   "group": "CRU",
    #                 "members" : [
    #                     {"tag": "CR_N8.0_b1.115_C4.3_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OA=="},
    #                     {"tag": "CR_N2.3_b0.807_C4.2_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MA=="},
    #                     {"tag": "CR_N3.7_b0.929_C4.2_s1", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MQ=="},
    #                     {"tag": "CR_N8.0_b1.115_C4.3_s0.51", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMg=="},
    #                     {"tag": "CR_N2.3_b0.807_C4.2_s0.51", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNg=="},
    #                     {"tag": "CR_N3.7_b0.929_C4.2_s0.51", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNw=="},
    #                     {"tag": "CR_N2.3_b0.807_C4.2_s1.62", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxOA=="},
    #                     {"tag": "CR_N8.0_b1.115_C4.3_s1.62", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMQ=="},
    #                     {"tag": "CR_N3.7_b0.929_C4.2_s1.62", "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNA=="}
    #                 ]
    #             },
    #             {   "group": "BG",
    #                 "members" : [
    #                     {"tag": "floor_addtot346ave", "toshi_id": "RmlsZToxMDIyMzA="}
    #                 ]
    #             }
    #         ]
    #     }
    # ]


    #NN-weighting
    permutations = [
        {
            "tag": "all rate combinations", "weight": 1.0,
            "permute" : [
                {   "group": "HIK",
                    "members" : [
                        {"tag": "HTC_b0.957_N16.5_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk0OQ=="},
                        {"tag": "HTC_b1.078_N22.8_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MA=="},
                        {"tag": "HTL_b0.957_N16.5_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1MQ=="},
                        {"tag": "HTL_b1.078_N22.8_C4.1_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mg=="},
                        {"tag": "HTC_b0.957_N16.5_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Mw=="},
                        {"tag": "HTC_b0.957_N16.5_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NA=="},
                        {"tag": "HTC_b1.078_N22.8_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1NQ=="},
                        {"tag": "HTC_b1.078_N22.8_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Ng=="},
                        {"tag": "HTL_b0.957_N16.5_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1Nw=="},
                        {"tag": "HTL_b0.957_N16.5_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OA=="},
                        {"tag": "HTL_b1.078_N22.8_C4.1_s0.54", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk1OQ=="},
                        {"tag": "HTL_b1.078_N22.8_C4.1_s1.43", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk2MA=="}
                    ]
                },
                {   "group": "PUY",
                    "members" : [
                        {"tag": "P_b0.75_N3.4_C3.9_s1", "weight":1.0, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3Ng=="}
                    ]
                },
                {   "group": "CRU",
                    "members" : [
                        {"tag": "CR_N8.0_b1.115_C4.3_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE3OA=="},
                        {"tag": "CR_N2.3_b0.807_C4.2_s1", "weight": 0.175, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MA=="},
                        {"tag": "CR_N3.7_b0.929_C4.2_s1", "weight": 0.35, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjE4MQ=="},
                        {"tag": "CR_N8.0_b1.115_C4.3_s0.51", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxMg=="},
                        {"tag": "CR_N2.3_b0.807_C4.2_s0.51", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNg=="},
                        {"tag": "CR_N3.7_b0.929_C4.2_s0.51", "weight": 0.075, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxNw=="},
                        {"tag": "CR_N2.3_b0.807_C4.2_s1.62", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIxOA=="},
                        {"tag": "CR_N8.0_b1.115_C4.3_s1.62", "weight": 0.0375, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyMQ=="},
                        {"tag": "CR_N3.7_b0.929_C4.2_s1.62", "weight": 0.075, "toshi_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjIyNA=="}
                    ]
                },
                {   "group": "BG",
                    "members" : [
                        {"tag": "floor_addtot346ave", "weight":1.0, "toshi_id": "RmlsZToxMDIyMzA="}
                    ]
                }
            ]
        }
    ]


    logging.basicConfig(level=logging.INFO)
    sources_folder = Path(WORK_PATH, 'sources')
    source_file_mapping = SourceModelLoader().unpack_sources(permutations, sources_folder)
    # print(source_file_mapping)

    ltbs = [ltb for ltb in get_logic_tree_branches(permutations)]

    print("LTB:", len(ltbs), ltbs[0])

    nrml = build_sources_xml(ltbs, source_file_mapping)

    with open("source_model.xml", 'w') as f:
        f.write(nrml)

    print('Done!')


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

