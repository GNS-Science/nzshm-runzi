#!oq_build_sources.py

import itertools
import logging
from pathlib import Path
from typing import Union, Dict, Any, Generator
import collections

import zipfile
from lxml import etree
from lxml.builder import ElementMaker # lxml only !

from nzshm_model.source_logic_tree import SourceLogicTree   # , FaultSystemLogicTree
from nzshm_model.source_logic_tree.version1.logic_tree import FlattenedSourceLogicTree
#from nzshm_model.nrml.logic_tree import NrmlDocument

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

def get_decomposed_logic_trees(
        srm_logic_tree: SourceLogicTree, slt_decomposition: str
) -> Generator[Union[SourceLogicTree, FlattenedSourceLogicTree], None, None]:
    """
    yield SourceLogicTree or FlattenedSourceLogicTree objects according to the decomposition scheme:
    'component': yield a SourceLogicTree with a single FaultSystem with a single Branch, for each component branch
    of the logic tree
    'composite': yield a FlattenedSourceLogicTree with a single CompositeBranch, for each branch of the flattened logic tree
    'none': do not decompose the logic tree, simply return the input logic tree.
    """

    if slt_decomposition not in ('none', 'composite', 'component'):
        raise ValueError("slt_decomposition must be one of 'none', 'composite', component'")
    
    if slt_decomposition == 'none':
        yield srm_logic_tree
    elif slt_decomposition == 'component':
        for fault_system in srm_logic_tree.fault_system_lts:
            for branch in fault_system.branches:
                branch.weight = 1.0
                fault_system_lt = FaultSystemLogicTree(
                    short_name=fault_system.short_name,
                    long_name=fault_system.long_name,
                    branches = [branch],
                )
                yield SourceLogicTree(
                    version=srm_logic_tree.version,
                    title=' '.join((fault_system.long_name, str(branch.values))),
                    fault_system_lts=[fault_system_lt],
                    correlations=[],
                )
    elif slt_decomposition == 'composite':
        for composite_branch in FlattenedSourceLogicTree.from_source_logic_tree(srm_logic_tree).branches:
            composite_branch.weight = 1.0
            
            # not necessary given how these are used, but this is to ensure any future
            # changes don't break due to inconsistant branch weights
            for branch in composite_branch.branches:
                branch.weight = 1.0

            yield FlattenedSourceLogicTree(
                version=srm_logic_tree.version,
                title=' '.join([srm_logic_tree.title] + [str(branch.values) for branch in composite_branch.branches]),
                branches=[composite_branch],
            )


# def get_logic_tree_file_ids(logic_tree: Union[SourceLogicTree, FlattenedSourceLogicTree]):

#     def get_ids(ids, branch, name=''):
#         if branch.onfault_nrml_id:
#             ids.add((':'.join((name, str(branch.values), 'IFM')), branch.onfault_nrml_id))
#         if branch.distributed_nrml_id:
#             ids.add((':'.join((name, str(branch.values), 'DSM')), branch.distributed_nrml_id))
#         return (ids)

#     ids = set()
#     if isinstance(logic_tree, SourceLogicTree):
#         for fault_system in logic_tree.fault_system_lts:
#             for branch in fault_system.branches:
#                 ids = get_ids(ids, branch, name=fault_system.short_name)
#     elif isinstance(logic_tree, FlattenedSourceLogicTree):
#         for composite_branch in logic_tree.branches:
#             for branch in composite_branch.branches:
#                 ids = get_ids(ids, branch)
    
#     return ids


# def get_ltb(group):
#     """NEW object-syle config"""
#     for obj in group['permute']:
#         yield [LogicTreeBranch(**source) for source in obj['members']]

# def get_logic_tree_branches(ltb_groups):
#     for group in ltb_groups: #List
#         for ltb in itertools.product(*get_ltb(group)):
#             yield ltb


def get_granular_logic_tree_branches(ltb_groups):
    """For granular we don't permute (YAY)."""
    for group in ltb_groups:
        for ltbs in get_ltb(group):
            for ltb in ltbs:
                d = ltb._asdict()
                d['weight'] = 1.0
                yield LogicTreeBranch(**d)


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


# class SourceModelLoader():

#     def __init__(self):
#         headers={"x-api-key":API_KEY}
#         self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

#     def unpack_sources(self, id_list, source_path):
#         """download and extract the sources given a list of nrml source IDs."""

#         sources = dict()
#         for src_name, nrml_id in id_list:
#             if nrml_id in sources.keys():
#                 continue

#             log.info(f"get src : {src_name} {nrml_id}")
#             gen = get_output_file_id(self._toshi_api, nrml_id)
#             source_nrml = download_files(self._toshi_api, gen, str(WORK_PATH), overwrite=False)
#             log.info(f"source_nrml: {source_nrml}")

#             with zipfile.ZipFile(source_nrml[nrml_id]['filepath'], 'r') as zip_ref:
#                 zip_ref.extractall(source_path)
#                 namelist = [name for name in zip_ref.namelist() if 'xml' in name]
#                 sources[nrml_id] = {'source_name': src_name, 'sources' : namelist}

#         return sources

#     def unpack_sources_in_list(self, nrml_ids, source_path):
#         """download and extract the sources given a list of NRML IDs."""

#         sources = dict()
#         for nrml_id in nrml_ids:
#             if nrml_id in sources.keys():
#                 raise ValueError('duplicates not expeceted nrml ids list')

#             log.info(f"get src: {nrml_id}")

#             gen = get_output_file_id(self._toshi_api, nrml_id)

#             source_nrml = download_files(self._toshi_api, gen, str(WORK_PATH), overwrite=False)
#             log.info(f"source_nrml: {source_nrml}")

#             with zipfile.ZipFile(source_nrml[nrml_id]['filepath'], 'r') as zip_ref:
#                 zip_ref.extractall(source_path)
#                 namelist = [name for name in zip_ref.namelist() if 'xml' in name]
#                 sources[nrml_id] = {'sources' : namelist}

#         return sources


# def build_sources_xml(nrml_doc: NrmlDocument, source_file_mapping: Dict[str, Any]) -> str:
#     """
#     Build a source model for a NRML logic tree object with their source files.
#     This will ultimatly be replaced by a nzhsm-model method for writing nrml files.
#     """
#     E = ElementMaker(namespace="http://openquake.org/xmlns/nrml/0.5",
#                       nsmap={"gml" : "http://www.opengis.net/gml", None:"http://openquake.org/xmlns/nrml/0.5"})
#     NRML = E.nrml
#     LT = E.logicTree
#     LTBL = E.logicTreeBranchingLevel
#     LTBS = E.logicTreeBranchSet
#     LTB = E.logicTreeBranch
#     UM = E.uncertaintyModel
#     UW = E.uncertaintyWeight

#     nrml = NRML()
#     extended_model = False
#     for logic_tree in nrml_doc.logic_trees:
#         lt = LT(logicTreeID=logic_tree.logicTreeID)
#         lt.text = None
#         ltbl = LTBL(brachingLevelID="1")
#         ltbl.text = None
#         for branch_set in logic_tree.branch_sets:
#             if extended_model:
#                 bs = LTBS(uncertaintyType="extendedModel", branchSetID=branch_set.branchSetID)
#             else:
#                 bs = LTBS(uncertaintyType=branch_set.uncertaintyType, branchSetID=branch_set.branchSetID)
#             extended_model = True
#             bs.text = None
#             for branch in branch_set.branches:
#                 b = LTB(UW(str(branch.uncertainty_weight)), branchID=branch.branchID)
#                 b.text = None
#                 files = ""
#                 for uncertainty_model in branch.uncertainty_models:
#                     files += '\t' + '\t'.join(source_file_mapping[uncertainty_model.toshi_nrml_id]['sources'])
#                 b.append(UM(files))
#                 bs.append(b)
#             ltbl.append(bs)
#         lt.append(ltbl)
#     nrml.append(lt)

#     return etree.tostring(nrml, pretty_print=True).decode()


# def build_disagg_sources_xml(source_files):
#     """Build a single branch source model for a list of source files."""
#     E = ElementMaker(namespace="http://openquake.org/xmlns/nrml/0.5",
#                       nsmap={"gml" : "http://www.opengis.net/gml", None:"http://openquake.org/xmlns/nrml/0.5"})
#     NRML = E.nrml
#     LT = E.logicTree
#     LTBS = E.logicTreeBranchSet
#     LTBL = E.logicTreeBranchingLevel
#     LTB = E.logicTreeBranch
#     UM = E.uncertaintyModel
#     UW = E.uncertaintyWeight

#     ltbs = LTBS(uncertaintyType="sourceModel", branchSetID="BS-NONCE1-DISAGG")

#     branch_name = "disaggregation sources"
#     branch_weight = "1.0"
#     files = "\t".join(source_files)
#     ltb = LTB( UM(files), UW(str(branch_weight)), branchID=branch_name)
#     ltbs.append(ltb)

#     nrml = NRML( LT( LTBL( ltbs, branchingLevelID="1" ), logicTreeID = "DISAGG"))
#     return etree.tostring(nrml, pretty_print=True).decode()


if __name__ == "__main__":
    #from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)
    from nzshm_model.source_logic_tree.version1.slt_config import from_config
    from nzshm_model.psha_adapter import OpenquakeSimplePshaAdapter
    import pathlib

    # from runzi.CONFIG.OQ import large_SLT_example_A #import logic_tree_permutations, gt_description
    
    config_path = pathlib.Path('runzi/CONFIG/OQ/large_SLT_example_A.py' )
    slt = SourceLogicTree.from_source_logic_tree(from_config(config_path)) #import and migrate to new version
    
    cache_folder = pathlib.Path('./SLT/CACHE')
    output_folder = pathlib.Path('./SLT/BUILD')

    cache_folder.mkdir(parents=True, exist_ok=True)
    output_folder.mkdir(parents=True, exist_ok=True)
    
    for branch in list(slt)[:1]:
        print(branch.values, branch.fslt.long_name, branch.slt.title)
        small_slt = SourceLogicTree.from_filtered_branches([branch])        
        adapter = small_slt.psha_adapter(provider=OpenquakeSimplePshaAdapter)
        adapter.write_config(cache_folder, output_folder)        
  

    print('Done!')
