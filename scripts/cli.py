import click
import toml

from runzi.automation.run_oq_disagg import run_oq_disagg_f
from runzi.automation.run_oq_hazard import run_oq_hazard_f

def load_config(config_filename: str):
    return toml.load(config_filename)

@click.group()
def rnz():
    pass

@rnz.command(name="oq-hazard", help="launch OpenQuake hazard calculation jobs")
@click.argument("config-filename", type=click.Path(exists=True))
def run_oq_hazard(config_filename):
    config = load_config(config_filename)
    run_oq_hazard_f(config)


@rnz.command(name="oq-disagg", help="launch OpenQuake disagg calculation jobs")
@click.argument("config-filename", type=click.Path(exists=True))
def run_oq_hazard(config_filename):
    config = load_config(config_filename)
    run_oq_disagg_f(config)


if __name__ == "__main__":
    rnz()  # pragma: no cover