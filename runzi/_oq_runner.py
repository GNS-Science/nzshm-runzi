"""OQ-venv-side helper. Executed by /opt/oq-venv/bin/python, NEVER imported from runzi.

This script wraps the OpenQuake UCERF converter. It is bundled inside the runzi
package directory so it can be located at runtime, but it is only ever executed
by the oq-venv Python interpreter — never imported from the runzi virtualenv.

openquake.* imports are deferred to function bodies so that syntax-checking or
accidental import from a venv that lacks OpenQuake does not raise ImportError.
"""

import argparse
import json
from pathlib import Path


def cmd_convert(args: argparse.Namespace) -> None:
    """Run UCERF -> OpenQuake XML conversion from a JSON config file.

    Args:
        args: Parsed CLI args; args.config is the path to the JSON config.
    """
    from openquake.converters.ucerf.parsers.sections_geojson import get_multi_fault_source
    from openquake.hazardlib.sourcewriter import write_source_model

    try:
        cfg = json.loads(Path(args.config).read_text())
    except FileNotFoundError as e:
        raise SystemExit(f'Config file not found: {args.config}') from e
    except json.JSONDecodeError as e:
        raise SystemExit(f'Invalid JSON in config: {e}') from e
    computed = get_multi_fault_source(
        cfg['src_folder'],
        cfg['dip_sd'],
        cfg['strike_sd'],
        cfg['source_id'],
        cfg['source_name'],
        cfg['tectonic_region_type'],
        cfg['investigation_time'],
        cfg['prefix'],
    )
    write_source_model(
        cfg['out_file'],
        [computed],
        name=cfg['source_name'],
        investigation_time=cfg['investigation_time'],
        prefix=cfg['prefix'],
    )


def main() -> None:
    """Parse CLI args and dispatch to subcommand."""
    p = argparse.ArgumentParser(description='OpenQuake venv-side helper for nzshm-runzi.')
    sub = p.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('convert', help='Convert a UCERF solution folder to an OpenQuake XML source model.')
    c.add_argument('--config', required=True, help='Path to the JSON config file.')
    c.set_defaults(func=cmd_convert)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
