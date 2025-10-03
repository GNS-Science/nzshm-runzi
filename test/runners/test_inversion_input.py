import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from runzi.runners.inversion_inputs import CrustalInversionArgs, SubductionInversionArgs

subduction_input_filepath = Path(__file__).parent.parent / "fixtures/runners/subduction_inversion.json"
crustal_input_filepath = Path(__file__).parent.parent / "fixtures/runners/crustal_inversion.json"


@pytest.fixture(scope='function')
def subduction_inv_data() -> dict:
    return json.loads(subduction_input_filepath.read_text())


@pytest.fixture(scope='function')
def subduction_inv_data_noweights() -> dict:
    data = json.loads(subduction_input_filepath.read_text())
    del data['task']['mfd_equality_weight']
    del data['task']['mfd_inequality_weight']
    del data['task']['mfd_eq_ineq_transition_mag']
    del data['task']['slip_rate_weighting_type']
    del data['task']['slip_rate_normalized_weight']
    del data['task']['slip_rate_unnormalized_weight']
    return data


@pytest.fixture(scope='function')
def crustal_inv_data() -> dict:
    return json.loads(crustal_input_filepath.read_text())


def test_from_json_file():
    """We can load the example input file."""
    inv_args = SubductionInversionArgs.from_json_file(subduction_input_filepath)
    assert inv_args


def test_tasks(subduction_inv_data):
    """We can iterate over tasks."""
    inv_args = SubductionInversionArgs(**subduction_inv_data)
    for count, task in enumerate(inv_args.get_tasks()):
        pass
    assert count + 1 == 4


data_mfd_unc = {
    'mfd_uncertainty_weight': [1.0, 2.0],
    'mfd_uncertainty_power': [1.0, 2.0],
    'mfd_uncertainty_scalar': [5.0, 6.0],
}
data_slip_unc = {
    'use_slip_scaling': [True, False],
    'slip_rate_uncertainty_weight': [1.0, 2.0],
    'slip_uncertainty_scaling_factor': [5.0, 6.0],
}
unc_data = [data_mfd_unc, data_slip_unc]


@pytest.mark.parametrize("extra_data", unc_data)
def test_compatable_weighting(subduction_inv_data, extra_data):
    """Test that incompatible weighting options raise errors."""
    subduction_inv_data['task'].update(extra_data)
    with pytest.raises(ValidationError) as e:
        SubductionInversionArgs(**subduction_inv_data)
        assert "Cannot combine" in str(e.value)


def test_reweight_missing(subduction_inv_data):
    """Test that reweighting without uncertainty options raises an error."""
    subduction_inv_data['task']['reweight'] = [True, False]
    with pytest.raises(ValidationError) as e:
        SubductionInversionArgs(**subduction_inv_data)
        assert "Re-weigting requires" in str(e.value)


def test_reweight(subduction_inv_data_noweights):
    """Test that reweighting with uncertainty options works."""
    subduction_inv_data_noweights['task']['reweight'] = [True, False]
    subduction_inv_data_noweights['task'].update(data_mfd_unc)
    subduction_inv_data_noweights['task'].update(data_slip_unc)
    assert SubductionInversionArgs(**subduction_inv_data_noweights)


weight_data_mfd = {
    'mfd_equality_weight': [1.0, 2.0],
}
weight_data_slip = {
    'slip_rate_weighting_type': ['normalized', 'unnormalized'],
}
weight_data = [weight_data_mfd, weight_data_slip]


@pytest.mark.parametrize("extra_data", weight_data)
def test_missing_weights(subduction_inv_data_noweights, extra_data):
    """Test that missing weight arguments raises an error."""
    subduction_inv_data_noweights['task'].update(extra_data)
    with pytest.raises(ValidationError) as e:
        SubductionInversionArgs(**subduction_inv_data_noweights)
        assert "must set all parameters" in str(e.value)


def test_crustal_input():
    """We can load the crustal example input file."""

    inv_args = CrustalInversionArgs.from_json_file(crustal_input_filepath)
    assert inv_args


def test_paleo_complete(crustal_inv_data):
    """If one paleo parameter is set, they all must be set."""
    del crustal_inv_data['task']['paleo_rate_constraint_weight']
    with pytest.raises(ValidationError) as e:
        CrustalInversionArgs(**crustal_inv_data)
        assert "must set all parameters" in str(e.value)


def test_crustal_tasks(crustal_inv_data):
    """We can iterate over tasks."""
    inv_args = CrustalInversionArgs(**crustal_inv_data)
    for count, task in enumerate(inv_args.get_tasks()):
        pass
    assert count + 1 == 6
