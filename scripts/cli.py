import click
import toml

import runzi.automation


def load_config(config_filename: str):
    return toml.load(config_filename)

@click.group()
def rnz():
    pass

@rnz.command(name="run-oq-hazard", help="launch OpenQuake hazard calculation jobs")
@click.argument("config-filename", type=click.Path(exists=True))
def run_oq_hazard(config_filename):
    config = load_config(config_filename)
    runzi.automation.run_oq_hazard_f(config)


if __name__ == "__main__":
    rnz()  # pragma: no cover