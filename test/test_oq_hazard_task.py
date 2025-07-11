import pytest

import runzi.execute.openquake.oq_hazard_task as oq_hazard_task_module
from runzi.execute.openquake.oq_hazard_task import BuilderTask
from nzshm_model.logic_tree import SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeConfig


FILE_ID = "ABCD"


class MockOpenQuakeHazardTask:
    input = None

    def complete_task(self, input_variables, metrics=None):
        self.input = input_variables


class MockToshiFile:
    def create_file(self, filepath, meta=None):
        return FILE_ID, "nshm.gns.cri.nz"

    def upload_content(self, post_url, filepath):
        pass


class MockToshiApi:
    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None):
        self.file = MockToshiFile()
        self.openquake_hazard_task = MockOpenQuakeHazardTask()


def test_run_executor(mocker):
    """
    Assert that the executor proeprty is set to the ECR digest after a hazard task run.
    We're pretty much mocking out everything that a task run calls to only verify
    the executor at the very end.
    """
    ecr_digest = "the-digest"
    mocker.patch.object(oq_hazard_task_module, "ECR_DIGEST", ecr_digest)
    mocker.patch.object(oq_hazard_task_module, "SPOOF_HAZARD", True)
    mocker.patch.object(oq_hazard_task_module, "ToshiApi", MockToshiApi)
    mocker.patch.object(oq_hazard_task_module, "TaskRelation")
    mocker.patch.object(oq_hazard_task_module, "SourceLogicTree")
    mocker.patch.object(oq_hazard_task_module, "NshmModel")
    mocker.patch.object(oq_hazard_task_module, "execute_openquake")
    mocker.patch.object(SourceLogicTree, "from_dict")
    mocker.patch.object(OpenquakeConfig, "from_dict")
    mocker.patch.object(BuilderTask, "_setup_automation_task")
    mocker.patch.object(BuilderTask, "set_site_parameters")
    mocker.patch.object(BuilderTask, "set_hazard_curve_parameters")

    task = BuilderTask({"use_api": True})

    task.run(
        {
            "task_type": "HAZARD",
            "hazard_model": {"srm_logic_tree": {}, "gmcm_logic_tree": {}, "hazard_config": {}},
            "general": {"title": "the-title", "description": "the-description"},
        },
        {"task_id": "the-task-id"},
    )

    assert task._toshi_api.openquake_hazard_task.input["executor"] == "ECRD:" + ecr_digest
