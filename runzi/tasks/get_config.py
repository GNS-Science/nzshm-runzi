import argparse
import json
import urllib.parse
from typing import Any


def get_config() -> dict[str, Any]:
    """Get the job config from a JSON string or file.

    Returns:
        the configuration for the job.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))
    except json.decoder.JSONDecodeError:
        # LOCAL and CLUSTER this is a file
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)

    return config
