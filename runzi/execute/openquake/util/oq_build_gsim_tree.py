#!oq_build_sources.py

import itertools
import logging
from pathlib import Path
import collections

import zipfile
from typing import Dict
from lxml import etree
from lxml.builder import ElementMaker # lxml only !

log = logging.getLogger(__name__)


transforms_map = dict(
    Stafford2022 = 'mu_branch',
    Atkinson2022 = 'epistemic',
    AbrahamsonGulerce2020 = 'region',
    KuehnEtAl2020 = 'region'
    )

def transform_gsims(gsims: Dict):
    """convert gsims ito form expected in NRML."""
    new_gsims = {}
    for trt, value in gsims.items():
        for name, arg_name in transforms_map.items():
            if name in value:
                n, a = value.split("_") # only two values allowed
                value = f'[{n}]\n{arg_name} = "{a}"'
            new_gsims[trt] = value
    return new_gsims


def build_gsim_xml(gsims):
    """Build a gsim model for the suppliced TRs."""
    E = ElementMaker(namespace="http://openquake.org/xmlns/nrml/0.5",
                      nsmap={"gml" : "http://www.opengis.net/gml", None:"http://openquake.org/xmlns/nrml/0.5"})
    NRML = E.nrml
    LT = E.logicTree
    LTBS = E.logicTreeBranchSet
    LTB = E.logicTreeBranch
    UM = E.uncertaintyModel
    UW = E.uncertaintyWeight

    logic_tree = LT()
    branch_sets = 0
    for tr, gsim in transform_gsims(gsims).items():
        bid = str(branch_sets)
        branch_set = LTBS(uncertaintyType="gmpeModel", branchSetID=bid, applyToTectonicRegionType=tr )
        branch_set.append( LTB( UM(gsim), UW("1.0"), branchID=bid))
        logic_tree.append(branch_set)
        branch_sets +=1

    nrml = NRML( logic_tree )
    return etree.tostring(nrml, pretty_print=True).decode()


if __name__ == "__main__":

    disagg_config = {
        "vs30": 400,
        "source_ids": [
            "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDc2NA==",
            "RmlsZToxMDEyMDU="
        ],
        "imt": "PGA",
        "agg": "mean",
        "poe": 0.02,
        "level": 0.3551166254050649,
        "location": "-36.870~174.770",
        "gsims": {
            "Subduction Interface": "Atkinson2022SInter_Central",
            "Subduction Intraslab": "KuehnEtAl2020SSlab_NZL",
            "Active Shallow Crust": "Atkinson2022Crust_Central"
        },
        "dist": 6.449359479798744e-08,
        "nearest_rlz": [
            "T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTc3:1",
            "T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTg0:1",
            "T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTg2:6",
            "T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTkz:4"
        ],
        "target_level": 0.3551165609114701
    }


    nrml = build_gsim_xml(disagg_config['gsims'])

    print(nrml)

    # with open("gsim_model.xml", 'w') as f:
    #     f.write(nrml)

    print('Done!')

    print()
