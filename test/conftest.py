import importlib.resources as resources
from typing import Any, Dict

import pytest

from runzi.automation.cli.cli import load_config


@pytest.fixture(scope='function')
def config_dict() -> Dict[str, Any]:
    ref = resources.files('test.fixtures.oq_hazard') / 'hazard.toml'
    with resources.as_file(ref) as config_path:
        return load_config(config_path)
