from runzi.automation.openquake.run_oq_hazard import run_oq_hazard, build_tasks
import runzi.automation.openquake.run_oq_hazard as run_oq_hazard_mod
from runzi.automation.scaling.local_config import EnvMode
from . import Spy

FILE_ID = "ABCD"

class MockToshiFile:

    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None):
        pass

    def create_file(self, filepath, meta=None):
        return FILE_ID, "nshm.gns.cri.nz"

def mock_schedule_tasks(scripts,worker_pool_size=None):
    pass


def build_tasks_mock(new_gt_id, args, task_type, model_type):
    return (1,2,3)

# if AWS mode, check that a file ID is added to the task arguments
def test_create_file(config, monkeypatch):

    config["site_params"]["locations_file"] = "sites.csv"
    del config["site_params"]["locations"]

    spy = Spy(build_tasks_mock)
    monkeypatch.setattr(run_oq_hazard_mod, "CLUSTER_MODE", EnvMode.AWS)
    monkeypatch.setattr(run_oq_hazard_mod, "ToshiFile", MockToshiFile)
    monkeypatch.setattr(run_oq_hazard_mod, "build_tasks", spy)
    monkeypatch.setattr(run_oq_hazard_mod, "schedule_tasks", mock_schedule_tasks)

    run_oq_hazard(config) 
    assert spy.calls[0]["args"][1]["site_params"]["locations_file_id"] == FILE_ID
