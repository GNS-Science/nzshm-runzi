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
# this is where we change source_model to use ~toshi_id~ (now inv_iod and bg_id)
LogicTreeBranch = collections.namedtuple('LogicTreeBranch', 'tag inv_id bg_id weight')


def get_logic_tree_file_ids(ltb_groups):
    ids = set()
    for group in ltb_groups: #List
        for sources in get_ltb(group):
            for source in sources:
                if source.inv_id:
                    ids.add( (source.tag, source.inv_id))
                if source.bg_id:
                    ids.add( (source.tag, source.bg_id))
    return list(ids)

def get_ltb(group):
    """NEW object-syle config"""
    for obj in group['permute']:
        yield [LogicTreeBranch(**source) for source in obj['members']]

def get_logic_tree_branches(ltb_groups):
    for group in ltb_groups: #List
        for ltb in itertools.product(*get_ltb(group)):
            yield ltb

def single_permutation(permutations, task_id):
    """
    A helper function to slice up a permuations list into it components, and retrun each as a mini-permutation object.
    Assumes that task_id relates to that length of the permutations passed in.
    """

    def single_source_branch_from(permutations, task_id):
        ltbs = [ltb for ltb in get_logic_tree_branches(permutations)]
        return ltbs[task_id]

    new_permutations = { "tag": "", "weight": 1.0, "permute" : [] }

    for member in single_source_branch_from(permutations, task_id):
        member = member._replace(weight = 1.0)
        obj = { "group": member.tag, "members" : [member._asdict()]}
        new_permutations['permute'].append(obj)
    return new_permutations





class SourceModelLoader():

    def __init__(self):
        headers={"x-api-key":API_KEY}
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    def unpack_sources(self, logic_tree_branch_permutations, source_path):
        """download and extract the sources."""

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

            # g = list(gen)
            # print(g)
            # assert 0

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

    def get_branch_sources(ltb):
        bs = ""
        if ltb.inv_id:
            bs += ltb.inv_id
        if ltb.bg_id:
            bs += f"|{ltb.bg_id}"
        return bs

    for branch in logic_tree_branches:
            files = ""
            branch_name = "|".join([get_branch_sources(ltb) for ltb in branch])
            branch_weight = 1.0
            for ltb in branch:
                #print(ltb)
                #name, src_id, wt = source_tuple
                if ltb.inv_id:
                    files += "\t".join(source_file_mapping[ltb.inv_id]['sources']) + "\t"
                if ltb.bg_id:
                    files += "\t".join(source_file_mapping[ltb.bg_id]['sources']) + "\t"
                branch_weight *= ltb.weight
            #branch_weight = round(branch_weight, 10)
            total_branch_weight += branch_weight
            ltb = LTB( UM(files), UW(str(branch_weight)), branchID=branch_name)
            ltbs.append(ltb)

    print(f'total_branch_weight: {total_branch_weight}')
    # assert round(total_branch_weight, 8) == 1.0

    nrml = NRML( LT( LTBL( ltbs, branchingLevelID="1" ), logicTreeID = "Combined"))
    return etree.tostring(nrml, pretty_print=True).decode()



if __name__ == "__main__":
    from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)

    from runzi.CONFIG.OQ.hik_n_sensitivity_config import logic_tree_permutations, gt_description
    # permutations =  [{
    #     "tag": "all sources, with polygons", "weight": 1.0,
    #     "permute" : [
    #         {   "group": "HIK",
    #             "members" : [
    #                 {"tag": "Hikurangi TC b=1.07, C=4.0, s=.75", "weight": 0.5,
    #                     "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4MQ==", "bg_id":"RmlsZToxMDQ4NjI="},
    #                 {"tag": "HTC_b0.957_N16.5_C4.1_s1", "weight": 0.5,
    #                     "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMjk0OQ==", "bg_id":"RmlsZToxMDQyOTY="}
    #             ]
    #         },
    #         {   "group": "PUY",
    #             "members" : [
    #                 {"tag": "Puysegur b=0.712, C=3.9, s=0.4", "weight":1.0,
    #                  "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDU4Mg==", "bg_id": None}
    #             ]
    #         },
    #         {   "group": "CRU",
    #             "members" : [
    #                 {"tag": "Crustal b=xxx, s=1.0", "weight": 1.0,
    #                     "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNDk3Mw==", "bg_id":"RmlsZToxMDQ4NjM="}
    #             ]
    #         }
    #     ]
    # }]

    permutations = logic_tree_permutations[0]

    print(permutations)

    logging.basicConfig(level=logging.INFO)
    sources_folder = Path(WORK_PATH, 'sources')
    # source_file_mapping = SourceModelLoader().unpack_sources(permutations, sources_folder)

    ltbs = [ltb for ltb in get_logic_tree_branches(permutations)]
    print("LTB 0:", ltbs[0])
    print()


    print(single_permutation(permutations, 0))


    nrml = build_sources_xml([ltbs[0]], source_file_mapping)

    with open("source_model.xml", 'w') as f:
        f.write(nrml)

    print('Done!')
