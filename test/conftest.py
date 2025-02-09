import importlib.resources as resources

import pytest

from scripts.cli import load_config


@pytest.fixture(scope='function')
def config():
    with resources.path('test.fixtures.oq_hazard', 'hazard.toml') as config_path:
        return load_config(config_path)
