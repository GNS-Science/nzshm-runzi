import json

from nzshm_model.logic_tree import SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeConfig

import runzi.execute.openquake.oq_hazard_task as oq_hazard_task_module
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.execute.openquake.oq_hazard_task import BuilderTask

FILE_ID = "ABCD"


class MockOpenQuakeHazardTask:
    complete_input_variables = None
    create_create_input_variables = None

    def complete_task(self, input_variables, metrics=None):
        self.complete_input_variables = input_variables

    def create_task(self, create_input_variables, arguments=None, environment=None, task_type=HazardTaskType.HAZARD):
        self.create_input_variables = create_input_variables


class MockToshiFile:
    def create_file(self, filepath, meta=None):
        return FILE_ID, "nshm.gns.cri.nz"

    def upload_content(self, post_url, filepath):
        pass


class MockToshiApi:
    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None):
        self.file = MockToshiFile()
        self.openquake_hazard_task = MockOpenQuakeHazardTask()


def test_run_executor(mocker, tmpdir):
    """
    Assert that the executor property is set to the ECR digest after a hazard task run.
    We're pretty much mocking out everything that a task run calls to only verify
    the executor at the very end.
    """
    ecr_digest = "the-digest"
    mocker.patch.object(oq_hazard_task_module, "ECR_DIGEST", ecr_digest)
    mocker.patch.object(oq_hazard_task_module, "SPOOF_HAZARD", True)
    mocker.patch.object(oq_hazard_task_module, "SPOOF_HAZARD", True)
    mocker.patch.object(oq_hazard_task_module, "WORK_PATH", tmpdir.mkdir("oq_hazard_task"))
    mocker.patch.object(oq_hazard_task_module, "ToshiApi", MockToshiApi)
    mocker.patch.object(oq_hazard_task_module, "TaskRelation")
    mocker.patch.object(oq_hazard_task_module, "SourceLogicTree")
    mocker.patch.object(oq_hazard_task_module, "NshmModel")
    mocker.patch.object(oq_hazard_task_module, "execute_openquake")
    mocker.patch.object(SourceLogicTree, "from_dict")
    mocker.patch.object(OpenquakeConfig, "from_dict")
    mocker.patch.object(BuilderTask, "set_site_parameters")
    mocker.patch.object(BuilderTask, "set_hazard_curve_parameters")

    task = BuilderTask({"use_api": True})

    srm_tree = {"logic_tree_version": 2}
    gmcm_tree = {"title": "gmcm-tree"}
    open_quake_config = {"oq_hazard_config": "value"}

    task.run(
        {
            "task_type": "HAZARD",
            "model_type": "the-model-type",
            "hazard_model": {
                "srm_logic_tree": srm_tree,
                "gmcm_logic_tree": gmcm_tree,
                "hazard_config": open_quake_config,
            },
            "general": {"title": "the-title", "description": "the-description"},
        },
        {"task_id": "the-task-id", "use_api": True, "general_task_id": "the-general-task-id"},
    )

    assert task._toshi_api.openquake_hazard_task.create_input_variables["srm_logic_tree"] == json.dumps(srm_tree)
    assert task._toshi_api.openquake_hazard_task.create_input_variables["gmcm_logic_tree"] == json.dumps(gmcm_tree)
    assert task._toshi_api.openquake_hazard_task.create_input_variables["openquake_config"] == json.dumps(
        open_quake_config
    )

    assert task._toshi_api.openquake_hazard_task.complete_input_variables["executor"] == "ECRD:" + ecr_digest
