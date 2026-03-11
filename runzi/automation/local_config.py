"""
This module exports comfiguration forthe current system
and is imported  by the various run_xxx.py scripts
"""

import enum
import os
from pathlib import Path

from dotenv import load_dotenv

from runzi.aws import get_secret

# fill environment variables from .env file if not yet set
load_dotenv()


class EnvMode(enum.Enum):
    LOCAL = "LOCAL"
    CLUSTER = "CLUSTER"
    AWS = "AWS"


def boolean_env(environ_name):
    return bool(os.getenv(environ_name, '').upper() in ["1", "Y", "YES", "TRUE"])


# API Setting are needed to store job details for later reference
USE_API = boolean_env('NZSHM22_TOSHI_API_ENABLED')
API_URL = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL', "http://localhost:4569")
ECR_DIGEST = os.getenv('NZSHM22_RUNZI_ECR_DIGEST')
THS_RLZ_DB = os.getenv('NZSHM22_THS_RLZ_DB')

CLUSTER_MODE = EnvMode.LOCAL  # set by --cluster-mode CLI option. This sets the default

# Get API key from AWS secrets manager
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
if not API_KEY:
    if 'TEST' in API_URL.upper():
        API_KEY = get_secret("NZSHM22_TOSHI_API_SECRET_TEST", "us-east-1").get("NZSHM22_TOSHI_API_KEY_TEST")
    elif 'PROD' in API_URL.upper():
        API_KEY = get_secret("NZSHM22_TOSHI_API_SECRET_PROD", "us-east-1").get("NZSHM22_TOSHI_API_KEY_PROD")
if USE_API and (not API_KEY):
    raise ValueError("No API key supplied. API key required if Toshi API enabled.")


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
