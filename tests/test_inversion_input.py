import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from runzi.tasks.inversion import CrustalInversionArgs, SubductionInversionArgs

subduction_input_filepath = Path(__file__).parent / "fixtures/subduction_inversion.json"
crustal_input_filepath = Path(__file__).parent / "fixtures/crustal_inversion.json"


@pytest.fixture(scope='function')
def subduction_inv_data() -> dict:
    return json.loads(subduction_input_filepath.read_text())


@pytest.fixture(scope='function')
def subduction_inv_data_noweights() -> dict:
    data = json.loads(subduction_input_filepath.read_text())
    del data['mfd_equality_weight']
    del data['mfd_inequality_weight']
    del data['mfd_eq_ineq_transition_mag']
    del data['slip_rate_weighting_type']
    del data['slip_rate_normalized_weight']
    del data['slip_rate_unnormalized_weight']
    return data


@pytest.fixture(scope='function')
def crustal_inv_data() -> dict:
    return json.loads(crustal_input_filepath.read_text())


data_mfd_unc = {
    'mfd_uncertainty_weight': 1.0,
    'mfd_uncertainty_power': 1.0,
    'mfd_uncertainty_scalar': 5.0,
}
data_slip_unc = {
    'use_slip_scaling': True,
    'slip_rate_uncertainty_weight': 1.0,
    'slip_uncertainty_scaling_factor': 5.0,
}
unc_data = [data_mfd_unc, data_slip_unc]


@pytest.mark.parametrize("extra_data", unc_data)
def test_compatable_weighting(subduction_inv_data, extra_data):
    """Test that incompatible weighting options raise errors."""
    subduction_inv_data.update(extra_data)
    with pytest.raises(ValidationError) as e:
        SubductionInversionArgs(**subduction_inv_data)
        assert "Cannot combine" in str(e.value)


def test_reweight_missing(subduction_inv_data):
    """Test that reweighting without uncertainty options raises an error."""
    subduction_inv_data['reweight'] = [True, False]
    with pytest.raises(ValidationError) as e:
        SubductionInversionArgs(**subduction_inv_data)
        assert "Re-weigting requires" in str(e.value)


def test_reweight(subduction_inv_data_noweights):
    """Test that reweighting with uncertainty options works."""
    subduction_inv_data_noweights['reweight'] = True
    subduction_inv_data_noweights.update(data_mfd_unc)
    subduction_inv_data_noweights.update(data_slip_unc)
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
    subduction_inv_data_noweights.update(extra_data)
    with pytest.raises(ValidationError) as e:
        SubductionInversionArgs(**subduction_inv_data_noweights)
        assert "must set all parameters" in str(e.value)


def test_paleo_complete(crustal_inv_data):
    """If one paleo parameter is set, they all must be set."""
    del crustal_inv_data['paleo_rate_constraint_weight']
    with pytest.raises(ValidationError) as e:
        CrustalInversionArgs(**crustal_inv_data)
        assert "must set all parameters" in str(e.value)
