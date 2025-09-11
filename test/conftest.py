import importlib.resources as resources
from pathlib import Path
from typing import Any, Dict, Union

import pytest
import tomlkit


def load_input(config_filename: Union[Path, str]) -> Dict[str, Any]:
    with Path(config_filename).open('r') as config_file:
        data = config_file.read()
    config = tomlkit.parse(data).unwrap()
    config["filepath"] = Path(config_filename).absolute()
    return config


@pytest.fixture(scope='function')
def hazard_input_dict() -> Dict[str, Any]:
    ref = resources.files('test.fixtures.oq_hazard') / 'hazard.toml'
    with resources.as_file(ref) as config_path:
        return load_input(config_path)


@pytest.fixture(scope='function')
def disagg_input_dict() -> Dict[str, Any]:
    ref = resources.files('test.fixtures.oq_hazard') / 'disagg.toml'
    with resources.as_file(ref) as config_path:
        return load_input(config_path)
