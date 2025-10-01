from pathlib import Path
import pytest
import json
from runzi.runners.inversion_inputs import SubductionInversionArgs

subduction_input_filepath = Path(__file__).parent.parent / "fixtures/runners/subduction_inversion.json"

@pytest.fixture(scope='function')
def subduction_inv_data() -> SubductionInversionArgs:
    return json.loads(subduction_input_filepath.read_text())


def test_subduction_from_json():
    inv_args = SubductionInversionArgs.from_json_file(subduction_input_filepath)
    assert inv_args

def test_subduction_tasks(subduction_inv_data):
    inv_args = SubductionInversionArgs(**subduction_inv_data)
    for count, task in enumerate(inv_args.get_tasks()):
        pass
    assert count + 1 == 4