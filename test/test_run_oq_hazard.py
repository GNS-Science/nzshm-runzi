import runzi.automation.openquake.run_oq_hazard as run_oq_hazard_module
from runzi.automation.openquake.run_oq_hazard import run_oq_hazard
from runzi.automation.scaling.local_config import EnvMode

FILE_ID = "ABCD"


class MockToshiFile:
    def create_file(self, filepath, meta=None):
        return FILE_ID, "nshm.gns.cri.nz"

    def upload_content(self, post_url, filepath):
        pass


class MockToshiApi:

    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None):
        self.file = MockToshiFile()


# if AWS mode, check that a file ID is added to the task arguments
def test_create_file(mocker, config_dict):

    config_dict["site_params"]["locations_file"] = "sites.csv"
    del config_dict["site_params"]["locations"]

    mocked_build_tasks = mocker.patch.object(run_oq_hazard_module, "build_tasks")
    mocker.patch.object(run_oq_hazard_module, "CLUSTER_MODE", EnvMode.AWS)
    mocker.patch.object(run_oq_hazard_module, "ToshiApi", MockToshiApi)
    mocker.patch.object(run_oq_hazard_module, "schedule_tasks")

    run_oq_hazard(config_dict)
    assert mocked_build_tasks.call_args.args[1]["site_params"]["locations_file_id"] == FILE_ID
