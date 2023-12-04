"""Function to build gsim XML for disaggs."""

import logging
from typing import Dict
from lxml import etree
from lxml.builder import ElementMaker # lxml only !

log = logging.getLogger(__name__)

# Depreciated
transforms_map = dict(
    Stafford2022 = 'mu_branch',
    Atkinson2022 = 'epistemic',
    AbrahamsonGulerce2020 = 'region',
    KuehnEtAl2020 = 'region'
    )

def transform_gsims(gsims: Dict):
    """Depreciated. convert gsims ito form expected in NRML."""
    new_gsims = {}
    for trt, value in gsims.items():
        for name, arg_name in transforms_map.items():
            if name in value:
                n, a = value.split("_") # only two values allowed
                value = f'[{n}]\n{arg_name} = "{a}"'
            new_gsims[trt] = value
    return new_gsims


def build_gsim_xml(gsims):
    # """Build a gsim model for the suppliced TRs."""
    # E = ElementMaker(namespace="http://openquake.org/xmlns/nrml/0.5",
    #                   nsmap={"gml" : "http://www.opengis.net/gml", None:"http://openquake.org/xmlns/nrml/0.5"})
    # NRML = E.nrml
    # LT = E.logicTree
    # LTBS = E.logicTreeBranchSet
    # LTB = E.logicTreeBranch
    # UM = E.uncertaintyModel
    # UW = E.uncertaintyWeight

    # logic_tree = LT()
    # branch_sets = 0
    # for tr, gsim in gsims.items():
    #     bid = str(branch_sets)
    #     branch_set = LTBS(uncertaintyType="gmpeModel", branchSetID=bid, applyToTectonicRegionType=tr )
    #     branch_set.append( LTB( UM(gsim), UW("1.0"), branchID=bid))
    #     logic_tree.append(branch_set)
    #     branch_sets +=1

    # nrml = NRML( logic_tree )
    # return etree.tostring(nrml, pretty_print=True).decode()
    return gsims


if __name__ == "__main__":

    disagg_config = {
        'level': 0.14000836650634893,
        'source_ids': ['SW52ZXJzaW9uU29sdXRpb25Ocm1sOjExODcxNw==',
        'RmlsZToxMjA5OTQ=',
        'SW52ZXJzaW9uU29sdXRpb25Ocm1sOjExNDQyNA==',
        'RmlsZToxMjEwMjE=',
        'RmlsZToxMjEwMzM=',
        'SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEyMDkxMQ==',
        'RmlsZToxMjA5ODU='],
        'gsims': {'Subduction Interface': '[Atkinson2022SInter]\nepistemic = "Upper"',
        'Subduction Intraslab': '[KuehnEtAl2020SSlab]\nregion = "GLO"\nsigma_mu_epsilon = 0.0',
        'Active Shallow Crust': '[CampbellBozorgnia2014]\nsigma_mu_epsilon = 0.0'},
        'rlz': ['T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDI4:0',
        'T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDMx:0',
        'T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDM5:9',
        'T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDQ0:13'],
        'hazard_ids': ['T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDI4',
        'T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDMx',
        'T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDM5',
        'T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTEzNDQ0'],
        'weight': 2.3061303136037524e-06,
        'dist': 2.6742413677754984e-05,
        'rank': 7
    }


    nrml = build_gsim_xml(disagg_config['gsims'])

    print(nrml)

    # with open("gsim_model.xml", 'w') as f:
    #     f.write(nrml)

    print('Done!')

    print()
