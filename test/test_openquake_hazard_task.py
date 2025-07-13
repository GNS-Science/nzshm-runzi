from nshm_toshi_client.toshi_client_base import ToshiClientBase

from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import OpenquakeHazardTask


class MockClient:
    def execute(self, query, variables):
        self.query = query
        self.variables = variables
        return {"update_openquake_hazard_task": {"openquake_hazard_task": {"id": None}}}


class MockToshiClientBase(ToshiClientBase):
    def __init__(self):
        self._client = MockClient()


def test_complete_task_executor(mocker):
    """
    Assserting that we pass the executor id to graphQL
    """
    executor_id = "the-executor-id"
    mock_api = MockToshiClientBase()
    openquake_hazard_task = OpenquakeHazardTask(mock_api)
    openquake_hazard_task.complete_task(
        openquake_hazard_task.get_example_complete_variables()
        | openquake_hazard_task.get_optional_complete_variables()
        | {"executor": executor_id}
    )

    assert mock_api._client.variables["executor"] == executor_id
