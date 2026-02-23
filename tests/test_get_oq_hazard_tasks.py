import json
from pathlib import Path

from nzshm_model import NshmModel, get_model_version
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeConfig

from runzi.arguments import ArgSweeper
from runzi.tasks.oq_hazard import OQHazardArgs, OQHazardJobRunner


def test_build_hazard_tasks():
    """Test that hazard models are correctly handled.

    - The SRM logic tree is split into one branch for each task.
    - The GMCM logic tree is specified by the model version.
    """
    input_filepath = Path(__file__).parent / "fixtures/hazard_job.json"
    input_data = json.loads(input_filepath.read_text())
    hazard_args = OQHazardArgs.model_validate(input_data, context={"base_path": input_filepath.parent.resolve()})

    job_input = ArgSweeper.from_config_file(input_filepath, OQHazardArgs)
    runner = OQHazardJobRunner(job_input)

    for num_tasks, task_args in enumerate(runner.argument_sweeper.get_tasks(), start=1):
        pass
    gmcm = task_args.gmcm_logic_tree
    srm = task_args.srm_logic_tree
    hazard_config = task_args.hazard_config

    model_expected = get_model_version(hazard_args.nshm_model_version)
    gmcm_expected = model_expected.gmm_logic_tree
    for num_branches, branch_expected in enumerate(model_expected.source_logic_tree, start=1):
        pass
    branch_expected.weight = 1.0
    srm_expected = SourceLogicTree.from_branches([branch_expected])
    hazard_config_expected = model_expected.hazard_config

    assert gmcm == gmcm_expected
    assert srm == srm_expected
    assert hazard_config == hazard_config_expected
    assert num_tasks == num_branches


def test_build_hazard_tasks_overwrite_model():
    """Test that we can over-write the logic trees and hazard config."""

    root_filepath = Path(__file__).parent / "fixtures"
    input_filepath = root_filepath / "hazard_job_overwrite.json"
    input_data = json.loads(input_filepath.read_text())
    job_input = ArgSweeper.from_config_file(input_filepath, OQHazardArgs)
    runner = OQHazardJobRunner(job_input)

    task_args = next(runner.argument_sweeper.get_tasks())
    gmcm = task_args.gmcm_logic_tree
    srm = task_args.srm_logic_tree
    hazard_config = task_args.hazard_config

    srm_overwrite = SourceLogicTree.from_json(root_filepath / input_data["srm_logic_tree"])
    gmcm_expected = GMCMLogicTree.from_json(root_filepath / input_data["gmcm_logic_tree"])
    hazard_config_expected = OpenquakeConfig.from_json(root_filepath / input_data["hazard_config"])
    model_expected = NshmModel("", "", srm_overwrite, gmcm_expected, hazard_config_expected)
    for branch_expected in model_expected.source_logic_tree:
        break
    branch_expected.weight = 1.0
    srm_expected = SourceLogicTree.from_branches([branch_expected])

    assert gmcm == gmcm_expected
    assert srm == srm_expected
    assert hazard_config == hazard_config_expected
