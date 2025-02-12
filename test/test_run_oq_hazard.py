import runzi.automation.openquake.run_oq_hazard as run_oq_hazard_module
from runzi.automation.openquake.run_oq_hazard import run_oq_hazard
from runzi.automation.scaling.local_config import EnvMode

from . import Spy

FILE_ID = "ABCD"


class MockToshiFile:
    def create_file(self, filepath, meta=None):
        return FILE_ID, "nshm.gns.cri.nz"

    def upload_content(self, post_url, filepath):
        pass


class MockToshiApi:

    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None):
        self.file = MockToshiFile()


def mock_schedule_tasks(scripts, worker_pool_size=None):
    pass


def build_tasks_mock(new_gt_id, args, task_type, model_type):
    return (1, 2, 3)


# if AWS mode, check that a file ID is added to the task arguments
def test_create_file(config_dict, monkeypatch):

    config_dict["site_params"]["locations_file"] = "sites.csv"
    del config_dict["site_params"]["locations"]

    spy = Spy(build_tasks_mock)
    monkeypatch.setattr(run_oq_hazard_module, "CLUSTER_MODE", EnvMode.AWS)
    monkeypatch.setattr(run_oq_hazard_module, "ToshiApi", MockToshiApi)
    monkeypatch.setattr(run_oq_hazard_module, "build_tasks", spy)
    monkeypatch.setattr(run_oq_hazard_module, "schedule_tasks", mock_schedule_tasks)

    run_oq_hazard(config_dict)
    assert spy.calls[0]["args"][1]["site_params"]["locations_file_id"] == FILE_ID
