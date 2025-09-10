import importlib.resources as resources
from typing import Any, Dict

import pytest

from runzi.automation.cli.cli import load_input


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
