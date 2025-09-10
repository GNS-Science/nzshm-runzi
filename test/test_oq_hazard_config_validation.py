import importlib.resources as resources
from test.helpers import does_not_raise

import pytest
from pydantic import ValidationError

from runzi.automation.openquake.config import DisaggInput, HazardInput


# default fixture should be a valid config
def test_config_validation(config_dict):
    HazardInput.model_validate(config_dict)


def test_config_valid_model_version(config_dict):
    config_dict["hazard_model"]["nshm_model_version"] = "NOT A VERSION"
    with pytest.raises(ValidationError):
        HazardInput.model_validate(config_dict)


# can specify logic trees using relative path from config file
def test_config_validation_lt_relpath(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_small.json"
    HazardInput.model_validate(config_dict)


# can specify logic trees using absolute path from config file
def test_config_validation_lt_abspath(config_dict):
    ref = resources.files('test.fixtures.oq_hazard') / 'gmcm_small.json'
    with resources.as_file(ref) as gmcm_path:
        config_dict["hazard_model"]["gmcm_logic_tree"] = str(gmcm_path.absolute())
    HazardInput.model_validate(config_dict)


# but the path must exist
def test_config_validation_lt_nopath(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_not_here.json"
    with pytest.raises(ValidationError):
        HazardInput.model_validate(config_dict)


# if a model version is not specified, 2 LTs and a hazard config are needed
def test_config_validation_lt_missing(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_small.json"
    del config_dict["hazard_model"]["nshm_model_version"]
    with pytest.raises(ValidationError):
        HazardInput.model_validate(config_dict)


# if a model version is not specified, 2 LTs and a hazard config are needed
def test_config_validation_lt_all(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_small.json"
    config_dict["hazard_model"]["srm_logic_tree"] = "srm_small.json"
    config_dict["hazard_model"]["hazard_config"] = "hazard_config.json"
    del config_dict["hazard_model"]["nshm_model_version"]
    HazardInput.model_validate(config_dict)


# can specify locations with a file
def test_config_validation_location_file(config_dict):
    del config_dict["site_params"]["locations"]
    config_dict["site_params"]["locations_file"] = "sites.csv"
    HazardInput.model_validate(config_dict)


# but not both a file and a list
def test_config_validation_location_listandfile(config_dict):
    config_dict["site_params"]["locations_file"] = "sites.csv"
    with pytest.raises(ValidationError):
        HazardInput.model_validate(config_dict)


# must specify one of locations and locations_file
def test_config_validation_location_or_listandfile(config_dict):
    del config_dict["site_params"]["locations"]
    with pytest.raises(ValidationError):
        HazardInput.model_validate(config_dict)


# if a uniform vs30 is not provided, the locations file must provide it
def test_config_validation_vs30_missing(config_dict):
    del config_dict["site_params"]["vs30s"]
    with pytest.raises(ValidationError):
        HazardInput.model_validate(config_dict)


def test_config_vs30(config_dict):
    del config_dict["site_params"]["locations"]
    config_dict["site_params"]["locations_file"] = "sites_vs30.csv"
    with pytest.raises(ValidationError):
        HazardInput.model_validate(config_dict)


# the vs30s are site specific and in the locations file
def test_config_validation_1(config_dict):
    del config_dict["site_params"]["locations"]
    del config_dict["site_params"]["vs30s"]
    config_dict["site_params"]["locations_file"] = "sites_vs30.csv"
    HazardInput.model_validate(config_dict)


table_param_value = [
    ("hazard_curve", "imts", "PGA"),
    ("hazard_curve", "imtls", 0.1),
    ("site_params", "vs30s", 100),
    ("site_params", "locations", "WLG"),
]


@pytest.mark.parametrize("table,param,value", table_param_value)
def test_coerce_to_list(config_dict, table, param, value):
    config_dict[table][param] = value
    HazardInput.model_validate(config_dict)


table_param_value_disagg = [
    ("hazard_curve", "aggs", "mean"),
    ("hazard_curve", "imts", "SA(1.0)"),
    ("disagg", "poes", 0.3),
]


@pytest.mark.parametrize("table,param,value", table_param_value_disagg)
def test_coerce_to_list_disagg(disagg_config_dict, table, param, value):
    disagg_config_dict[table][param] = value
    DisaggInput.model_validate(disagg_config_dict)


def test_disagg_config_validation(disagg_config_dict):
    DisaggInput.model_validate(disagg_config_dict)


nvb = [
    ("mag_bin_width", 0.1, {"mag": [5.1, 5.2]}),
    ("distance_bin_width", 10.0, {"dist": [100, 200]}),
    ("coordinate_bin_width", 10.0, {"lon": [100, 200]}),
    ("coordinate_bin_width", 10.0, {"lat": [100, 200]}),
    ("num_epsilon_bins", 4, {"eps": [0.1, 0.2]}),
]


@pytest.mark.parametrize("name,value,bin_edges", nvb)
def test_disagg_bins(disagg_config_dict, name, value, bin_edges):
    disagg_config_dict["disagg"][name] = value
    disagg_config_dict["disagg"]["disagg_bin_edges"] = bin_edges
    with pytest.raises(ValidationError):
        DisaggInput.model_validate(disagg_config_dict)


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
def test_disagg_types(disagg_config_dict, disagg_outputs, name, value, expectation):
    disagg_config_dict["disagg"][name] = value
    disagg_config_dict["disagg"]["disagg_outputs"] = disagg_outputs
    with expectation:
        DisaggInput.model_validate(disagg_config_dict)


# the aggs must be present in AggregationEnum
def test_disagg_incorrect_agg(disagg_config_dict):
    disagg_config_dict["hazard_curve"]["aggs"] = ["PGA", "XYZ"]
    with pytest.raises(ValidationError):
        DisaggInput.model_validate(disagg_config_dict)
