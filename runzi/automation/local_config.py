"""
This module exports comfiguration forthe current system
and is imported  by the various run_xxx.py scripts
"""

import enum
import logging
import os
from pathlib import Path

# fill environment variables from .env file if not yet set
# this must be done before importing constants from nshm_toshi_client to ensure .env values are used
from dotenv import load_dotenv

load_dotenv()

from nshm_toshi_client import API_URL, M2M_SECRET_ARN, S3_URL, get_auth_kwargs  # noqa: F401, E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class ClusterModeEnum(enum.Enum):
    LOCAL = "LOCAL"
    CLUSTER = "CLUSTER"
    AWS = "AWS"


def boolean_env(environ_name):
    return bool(os.getenv(environ_name, '').upper() in ["1", "Y", "YES", "TRUE"])


# API Setting are needed to store job details for later reference
USE_API = boolean_env('NZSHM22_TOSHI_API_ENABLED')
ECR_DIGEST = os.getenv('NZSHM22_RUNZI_ECR_DIGEST')
THS_RLZ_DB = os.getenv('NZSHM22_THS_RLZ_DB')

DEFAULT_CLUSTER_MODE = ClusterModeEnum.LOCAL
# the value of this variable can be changed by the CLI but we set it here in-case it's being accessed w/o the CLI
CLUSTER_MODE = DEFAULT_CLUSTER_MODE

# How many jobs to run in parallel - keep thread/memory resources in mind
WORKER_POOL_SIZE = int(os.getenv('NZSHM22_SCRIPT_WORKER_POOL_SIZE', 1))

# Memory settings, be careful - don't exceed what you have avail, or you'll see swapping!
JVM_HEAP_START = int(os.getenv('NZSHM22_SCRIPT_JVM_HEAP_START', 4))  # Startup JAVA Memory (per worker)

# LOCAL SYSTEM SETTINGS
OPENSHA_ROOT = Path(os.getenv('NZSHM22_OPENSHA_ROOT', "~/DEV/GNS/opensha-modular"))
OPENSHA_JRE = Path(os.getenv('NZSHM22_OPENSHA_JRE', "/usr/lib/jvm/java-11-openjdk-amd64/bin/java"))
FATJAR = Path(os.getenv('NZSHM22_FATJAR', OPENSHA_ROOT))
WORK_PATH = Path(os.getenv('NZSHM22_SCRIPT_WORK_PATH', Path.cwd() / "tmp"))

BUILD_PLOTS = boolean_env('NZSHM22_BUILD_PLOTS')
REPORT_LEVEL = os.getenv('NZSHM22_REPORT_LEVEL', None)  # None, LIGHT, DEFAULT, FULL
HACK_FAULT_MODEL = os.getenv('NZSHM22_HACK_FAULT_MODEL')

# S3 report bucket name
S3_REPORT_BUCKET = os.getenv('NZSHM22_S3_REPORT_BUCKET', "None")
S3_UPLOAD_WORKERS = int(os.getenv('NZSHM22_S3_UPLOAD_WORKERS', 50))

SPOOF = boolean_env('SPOOF')

# OpenQuake environment settings
OQ_VENV = os.getenv('NZSHM22_OQ_VENV')
OQ_DATADIR = os.getenv('NZSHM22_OQ_DATADIR')
