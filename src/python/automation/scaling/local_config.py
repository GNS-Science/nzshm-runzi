"""
This module exports comfiguration forthe current system
and is imported  by the various run_xxx.py scripts
"""

import os
from pathlib import PurePath

#API Setting are needed to sore job details for later reference
API_URL  = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL',"http://localhost:4569")

USE_API = os.getenv('NZSHM22_TOSHI_API_ENABLED' , False) == "1"

#How many threads to give each worker, setting this higher than # of virtual cores is pointless.
JAVA_THREADS = os.getenv('NZSHM22_SCRIPT_JAVA_THREADS', 4) #each

#How many jobs to run in parallel - keep thread/memory resources in mind
WORKER_POOL_SIZE = os.getenv('NZSHM22_SCRIPT_WORKER_POOL_SIZE',  2)

#Memory settings, be careful - don't exceed what you have avail, or you'll see swapping!
JVM_HEAP_START = os.getenv('NZSHM22_SCRIPT_JVM_HEAP_START', 4) #Startup JAVA Memory (per worker)
JVM_HEAP_MAX = os.getenv('NZSHM22_SCRIPT_JVM_HEAP_MAX', 10)  #Maximum JAVA Memory (per worker)


#LOCAL SYSTEM SETTINGS
OPENSHA_ROOT = os.getenv('NZSHM22_OPENSHA_ROOT', "~/DEV/GNS/opensha-new")
OPENSHA_JRE = os.getenv('NZSHM22_OPENSHA_JRE', "/usr/lib/jvm/java-11-openjdk-amd64/bin/java")
FATJAR = os.getenv('NZSHM22_FATJAR', None) or str(PurePath(OPENSHA_ROOT, "nshm-nz-opensha/build/libs/nshm-nz-opensha-all.jar"))
WORK_PATH = os.getenv('NZSHM22_SCRIPT_WORK_PATH', PurePath(os.getcwd(), "tmp"))

CLUSTER_MODE = os.getenv('NZSHM22_SCRIPT_CLUSTER_MODE', False)
