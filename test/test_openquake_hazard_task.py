from nshm_toshi_client.toshi_client_base import ToshiClientBase

from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import OpenquakeHazardTask


class MockClient:
    def __init__(self, result):
        self.result = result

    def execute(self, query, variables):
        self.query = query
        self.variables = variables
        return self.result


class MockToshiClientBase(ToshiClientBase):
    def __init__(self, result):
        self._client = MockClient(result)


def test_complete_task_executor(mocker):
    """
    Assserting that we pass the executor id to graphQL
    """
    executor_id = "the-executor-id"
    mock_api = MockToshiClientBase({"update_openquake_hazard_task": {"openquake_hazard_task": {"id": None}}})
    openquake_hazard_task = OpenquakeHazardTask(mock_api)
    openquake_hazard_task.complete_task(
        openquake_hazard_task.get_example_complete_variables()
        | openquake_hazard_task.get_optional_complete_variables()
        | {"executor": executor_id}
    )

    assert mock_api._client.variables["executor"] == executor_id


def test_create_task_inputs(mocker):
    """
    Assserting that we pass the correct inputs to graphQL
    """
    srm_logic_tree = "the-srm-logic-tree"
    gmcm_logic_tree = "the-gmcm-logic-tree"
    openquake_config = "the-openquake-config"
    mock_api = MockToshiClientBase({"create_openquake_hazard_task": {"openquake_hazard_task": {"id": None}}})
    openquake_hazard_task = OpenquakeHazardTask(mock_api)
    openquake_hazard_task.create_task(
        openquake_hazard_task.get_example_create_variables()
        | {"srm_logic_tree": srm_logic_tree, "gmcm_logic_tree": gmcm_logic_tree, "openquake_config": openquake_config}
    )

    assert mock_api._client.variables["srm_logic_tree"] == srm_logic_tree
    assert mock_api._client.variables["gmcm_logic_tree"] == gmcm_logic_tree
    assert mock_api._client.variables["openquake_config"] == openquake_config
