import pytest
import runzi.automation.openquake.run_oq_hazard as run_oq_hazard_module
from runzi.automation.openquake.run_oq_hazard import run_oq_hazard
from runzi.automation.scaling.local_config import EnvMode

FILE_ID = "ABCD"


class MockToshiFile:
    def create_file(self, filepath, meta=None):
        return FILE_ID, "nshm.gns.cri.nz"

    def upload_content(self, post_url, filepath):
        pass


class MockGeneralTask:
    def create_task(self, args):
        pass


class MockToshiApi:

    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None):
        self.file = MockToshiFile()
        self.general_task = MockGeneralTask()


# check that file IDs are added to the task arguments
def test_create_file(mocker, config_dict):

    config_dict["site_params"]["locations_file"] = "sites.csv"
    del config_dict["site_params"]["locations"]

    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_small.json"
    config_dict["hazard_model"]["srm_logic_tree"] = "srm_small.json"

    mocked_build_tasks = mocker.patch.object(run_oq_hazard_module, "build_tasks")
    mocker.patch.object(run_oq_hazard_module, "USE_API", True)
    mocker.patch.object(run_oq_hazard_module, "CLUSTER_MODE", EnvMode.AWS)
    mocker.patch.object(run_oq_hazard_module, "ToshiApi", MockToshiApi)
    mocker.patch.object(run_oq_hazard_module, "schedule_tasks")

    run_oq_hazard(config_dict)
    assert mocked_build_tasks.call_args.args[1]["site_params"]["locations_file_id"] == FILE_ID
    assert mocked_build_tasks.call_args.args[1]["hazard_model"]["gmcm_logic_tree_id"] == FILE_ID
    assert mocked_build_tasks.call_args.args[1]["hazard_model"]["srm_logic_tree_id"] == FILE_ID


def test_consistent_setup(mocker, config_dict):

    config_dict["site_params"]["locations_file"] = "sites.csv"
    del config_dict["site_params"]["locations"]

    mocker.patch.object(run_oq_hazard_module, "build_tasks")
    mocker.patch.object(run_oq_hazard_module, "USE_API", False)
    mocker.patch.object(run_oq_hazard_module, "CLUSTER_MODE", EnvMode.AWS)
    mocker.patch.object(run_oq_hazard_module, "ToshiApi", MockToshiApi)
    mocker.patch.object(run_oq_hazard_module, "schedule_tasks")

    with pytest.raises(AssertionError) as excinfo:
        run_oq_hazard(config_dict)
    assert "Toshi API must be enabled when cluster mode is AWS" in str(excinfo.value)
