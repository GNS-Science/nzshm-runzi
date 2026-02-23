import importlib.resources as resources
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from runzi.tasks.oq_hazard import OQDisaggArgs, OQHazardArgs
from tests.helpers import does_not_raise


@pytest.fixture(scope='function')
def hazard_input_data():
    ref = resources.files('tests.fixtures') / 'hazard_job.json'
    with resources.as_file(ref) as input_path:
        return json.loads(input_path.read_text())


@pytest.fixture(scope='function')
def disagg_input_data():
    ref = resources.files('tests.fixtures') / 'disagg_job.json'
    with resources.as_file(ref) as input_path:
        return json.loads(input_path.read_text())


def test_from_json():
    ref = resources.files('tests.fixtures') / 'hazard_job.json'
    with resources.as_file(ref) as input_path:
        assert OQHazardArgs.model_validate_json(input_path.read_text())


def test_config_validation(hazard_input_data):
    """default fixture should be a valid config"""
    OQHazardArgs.model_validate(hazard_input_data)


def test_config_valid_model_version(hazard_input_data):
    hazard_input_data["nshm_model_version"] = "NOT A VERSION"
    with pytest.raises(ValidationError):
        OQHazardArgs.model_validate(hazard_input_data)


def test_config_validation_lt_file(hazard_input_data):
    """can specify logic trees using relative path from config file"""
    hazard_input_data["gmcm_logic_tree"] = Path(__file__).parent / "fixtures/gmcm_small.json"
    OQHazardArgs.model_validate(hazard_input_data)


def test_config_validation_lt_nopath(hazard_input_data):
    """but the path must exist"""
    hazard_input_data["gmcm_logic_tree"] = "gmcm_not_here.json"
    with pytest.raises(ValidationError) as err:
        OQHazardArgs.model_validate(hazard_input_data)
    assert re.search("file .* does not exist", str(err.value))


def test_config_validation_lt_missing(hazard_input_data):
    """if a model version is not specified, 2 LTs and a hazard config are needed"""
    hazard_input_data["gmcm_logic_tree"] = Path(__file__).parent / "fixtures/gmcm_small.json"
    hazard_input_data.pop("nshm_model_version")
    with pytest.raises(ValidationError) as err:
        OQHazardArgs.model_validate(hazard_input_data)
    assert "if nshm_model_version not specified, must provide" in str(err.value)


def test_config_validation_lt_all(hazard_input_data):
    """if a model version is not specified, 2 LTs and a hazard config are needed"""
    hazard_input_data["gmcm_logic_tree"] = Path(__file__).parent / "fixtures/gmcm_small.json"
    hazard_input_data["srm_logic_tree"] = Path(__file__).parent / "fixtures/srm_small.json"
    hazard_input_data["hazard_config"] = Path(__file__).parent / "fixtures/hazard_config.json"
    hazard_input_data.pop("nshm_model_version")
    OQHazardArgs.model_validate(hazard_input_data)


def test_config_validation_location_file(hazard_input_data):
    """can specify locations with a file"""
    hazard_input_data.pop("locations")
    hazard_input_data["locations_file"] = Path(__file__).parent / "fixtures/sites.csv"
    OQHazardArgs.model_validate(hazard_input_data)


def test_config_validation_location_listandfile(hazard_input_data):
    """but not both a file and a list"""
    hazard_input_data["locations_file"] = Path(__file__).parent / "fixtures/sites.csv"
    with pytest.raises(ValidationError) as err:
        OQHazardArgs.model_validate(hazard_input_data)
    assert "cannot specify both locations and locations_file" in str(err.value)


def test_config_validation_location_or_listandfile(hazard_input_data):
    """must specify one of locations and locations_file"""
    hazard_input_data.pop("locations")
    with pytest.raises(ValidationError) as err:
        OQHazardArgs.model_validate(hazard_input_data)
    assert "must specify one of locations or locations_file" in str(err.value)


def test_config_validation_vs30_missing(hazard_input_data):
    """if a uniform vs30 is not provided, the locations file must provide it"""
    hazard_input_data.pop("vs30")
    with pytest.raises(ValidationError) as err:
        OQHazardArgs.model_validate(hazard_input_data)
    assert "locations file must have vs30 column if uniform vs30 not given" in str(err.value)


def test_config_vs30(hazard_input_data):
    hazard_input_data.pop("locations")
    hazard_input_data["locations_file"] = Path(__file__).parent / "fixtures/sites_vs30.csv"
    with pytest.raises(ValidationError) as err:
        OQHazardArgs.model_validate(hazard_input_data)
    assert "cannot specify both uniform and site-specific vs30" in str(err.value)


def test_config_validation_1(hazard_input_data):
    """the vs30s are site specific and in the locations file"""
    hazard_input_data.pop("locations")
    hazard_input_data.pop("vs30")
    hazard_input_data["locations_file"] = Path(__file__).parent / "fixtures/sites_vs30.csv"
    OQHazardArgs.model_validate(hazard_input_data)


def test_disagg_config_validation(disagg_input_data):
    OQDisaggArgs.model_validate(disagg_input_data)


nvbe = [
    ("mag_bin_width", 0.1, {"mag": [5.1, 5.2]}, "cannot specify mag_bin_width and mag bin edges"),
    ("distance_bin_width", 10.0, {"dist": [100, 200]}, "cannot specify distance_bin_width and dist bin edges"),
    ("coordinate_bin_width", 10.0, {"lon": [100, 200]}, "cannot specify coordinate_bin_width and lon bin edges"),
    ("coordinate_bin_width", 10.0, {"lat": [100, 200]}, "cannot specify coordinate_bin_width and lat bin edges"),
    ("num_epsilon_bins", 4, {"eps": [0.1, 0.2]}, "cannot specify num_epsilon_bins and eps bin edges"),
]


@pytest.mark.parametrize("name,value,bin_edges,error_message", nvbe)
def test_disagg_bins(disagg_input_data, name, value, bin_edges, error_message):
    disagg_input_data[name] = value
    disagg_input_data["disagg_bin_edges"] = bin_edges
    with pytest.raises(ValidationError) as err:
        OQDisaggArgs.model_validate(disagg_input_data)
    assert error_message in str(err.value)


"TRT Mag Dist Mag_Dist TRT_Mag_Dist_Eps"


@pytest.mark.parametrize(
    "disagg_outputs,name,value,expectation",
    [
        (["Mag"], "disagg_bin_edges", {"mag": [5.1, 5.2]}, does_not_raise()),
        (["Mag"], "mag_bin_width", 0.1, does_not_raise()),
        (["Mag"], "dist_bin_width", 10.0, pytest.raises(ValidationError)),
        (["Dist"], "disagg_bin_edges", {"dist": [5.1, 5.2]}, does_not_raise()),
        (["Dist"], "distance_bin_width", 0.2, does_not_raise()),
        (["Dist"], "mag_bin_width", 10.0, pytest.raises(ValidationError)),
        (["Eps"], "disagg_bin_edges", {"eps": [5.1, 5.2]}, does_not_raise()),
        (["Eps"], "num_epsilon_bins", 2, does_not_raise()),
        (["Eps"], "dist_bin_width", 10.0, pytest.raises(ValidationError)),
        (["Lon"], "disagg_bin_edges", {"lon": [5.1, 5.2]}, does_not_raise()),
        (["Lon"], "coordinate_bin_width", 0.3, does_not_raise()),
        (["Lon"], "dist_bin_width", 10.0, pytest.raises(ValidationError)),
        (["Lat"], "disagg_bin_edges", {"lat": [5.1, 5.2]}, does_not_raise()),
        (["Lat"], "coordinate_bin_width", 0.4, does_not_raise()),
        (["Lat"], "dist_bin_width", 10.0, pytest.raises(ValidationError)),
        (["Lat"], "disagg_bin_edges", {"error": [5.1, 5.2]}, pytest.raises(ValidationError)),
        (["Lat"], "nonexistent_bin_width", 10.0, pytest.raises(ValidationError)),
        (["Error"], "dist_bin_width", 10.0, pytest.raises(ValidationError)),
    ],
)
def test_disagg_types(disagg_input_data, disagg_outputs, name, value, expectation):
    disagg_input_data.pop("mag_bin_width")
    disagg_input_data.pop("distance_bin_width")
    disagg_input_data.pop("coordinate_bin_width")
    disagg_input_data.pop("num_epsilon_bins")
    disagg_input_data.pop("disagg_bin_edges")
    disagg_input_data[name] = value
    disagg_input_data["disagg_types"] = disagg_outputs
    with expectation:
        OQDisaggArgs.model_validate(disagg_input_data)


def test_disagg_incorrect_agg(disagg_input_data):
    """the aggs must be present in AggregationEnum"""
    disagg_input_data["agg"] = ["PGA", "XYZ"]
    with pytest.raises(ValidationError):
        OQDisaggArgs.model_validate(disagg_input_data)
