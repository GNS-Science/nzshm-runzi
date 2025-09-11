from pathlib import Path

from nzshm_model import NshmModel, get_model_version
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeConfig

import runzi.configuration.openquake.oq_hazard as coh
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.configuration.openquake.oq_hazard import build_hazard_tasks


def build_task_mock(task_arguments, job_arguments, task_id, extra_env):
    pass


# if nshm_model_version, check hazard config, gmcm, and 1 srm
def test_build_hazard_tasks_model_version(mocker, hazard_input_dict):

    mocked_build_task = mocker.patch.object(coh, "build_task")
    for script_file in build_hazard_tasks("ABC", SubtaskType.OPENQUAKE_HAZARD, ModelType.COMPOSITE, hazard_input_dict):
        pass
    task_args = mocked_build_task.call_args_list[-1].args[0]
    gmcm = GMCMLogicTree.from_dict(task_args["hazard_model"]["gmcm_logic_tree"])
    srm = SourceLogicTree.from_dict(task_args["hazard_model"]["srm_logic_tree"])
    hazard_config = OpenquakeConfig.from_dict(task_args["hazard_model"]["hazard_config"])

    model_expected = get_model_version(hazard_input_dict["hazard_model"]["nshm_model_version"])
    gmcm_expected = model_expected.gmm_logic_tree
    for i, branch_expected in enumerate(model_expected.source_logic_tree):
        pass
    branch_expected.weight = 1.0
    srm_expected = SourceLogicTree.from_branches([branch_expected])
    hazard_config_expected = model_expected.hazard_config

    assert gmcm == gmcm_expected
    assert srm == srm_expected
    assert hazard_config == hazard_config_expected
    assert len(mocked_build_task.call_args_list) == i + 1


# if overwrite gmcm, srm, or hazard config, check that they are changed
def test_build_hazard_tasks_overwrite_model(mocker, hazard_input_dict):

    root_path = Path(hazard_input_dict["filepath"]).parent

    hazard_input_dict["hazard_model"]["gmcm_logic_tree"] = str(root_path / "gmcm_small.json")
    hazard_input_dict["hazard_model"]["srm_logic_tree"] = str(root_path / "srm_small.json")
    hazard_input_dict["hazard_model"]["hazard_config"] = str(root_path / "hazard_config.json")

    mocked_build_task = mocker.patch.object(coh, "build_task")
    _ = next(build_hazard_tasks("ABC", SubtaskType.OPENQUAKE_HAZARD, ModelType.COMPOSITE, hazard_input_dict))
    task_args = mocked_build_task.call_args_list[0].args[0]
    gmcm = GMCMLogicTree.from_dict(task_args["hazard_model"]["gmcm_logic_tree"])
    srm = SourceLogicTree.from_dict(task_args["hazard_model"]["srm_logic_tree"])
    hazard_config = OpenquakeConfig.from_dict(task_args["hazard_model"]["hazard_config"])

    srm_overwrite = SourceLogicTree.from_json(root_path / "srm_small.json")
    gmcm_expected = GMCMLogicTree.from_json(root_path / "gmcm_small.json")
    hazard_config_expected = OpenquakeConfig.from_json(root_path / "hazard_config.json")
    model_expected = NshmModel("", "", srm_overwrite, gmcm_expected, hazard_config_expected)
    for branch_expected in model_expected.source_logic_tree:
        break
    branch_expected.weight = 1.0
    srm_expected = SourceLogicTree.from_branches([branch_expected])

    assert gmcm == gmcm_expected
    assert srm == srm_expected
    assert hazard_config == hazard_config_expected
