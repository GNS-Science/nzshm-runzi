import argparse
import json
import urllib.parse
from typing import Any

from runzi.aws import decompress_config


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
        try:
            # for AWS this may instead be an LZMA+base64 compressed JSON string
            # (used when the quoted form would exceed Batch's containerOverrides limit)
            config = json.loads(decompress_config(args.config))
        except Exception:
            # LOCAL and CLUSTER this is a file
            f = open(args.config, encoding='utf-8')
            config = json.load(f)

    return config
