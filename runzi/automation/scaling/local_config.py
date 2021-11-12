"""
This module exports comfiguration forthe current system
and is imported  by the various run_xxx.py scripts
"""

import os
import enum
from pathlib import PurePath

class EnvMode(enum.IntEnum):
    LOCAL = 0
    CLUSTER = 1
    AWS = 2

#API Setting are needed to sore job details for later reference
API_URL  = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL',"http://localhost:4569")

USE_API = os.getenv('NZSHM22_TOSHI_API_ENABLED' , False) == "1"

#How many threads to give each worker, setting this higher than # of virtual cores is pointless.
JAVA_THREADS = os.getenv('NZSHM22_SCRIPT_JAVA_THREADS', 4) #each

#How many jobs to run in parallel - keep thread/memory resources in mind
WORKER_POOL_SIZE = os.getenv('NZSHM22_SCRIPT_WORKER_POOL_SIZE',  2)
#How many files to upload to S3 in parallel
AGENT_S3_WORKERS = os.getenv('NZSHM22_SCRIPT_AWS_S3_WORKERS',  50)

#Memory settings, be careful - don't exceed what you have avail, or you'll see swapping!
JVM_HEAP_START = os.getenv('NZSHM22_SCRIPT_JVM_HEAP_START', 4) #Startup JAVA Memory (per worker)
JVM_HEAP_MAX = os.getenv('NZSHM22_SCRIPT_JVM_HEAP_MAX', 10)  #Maximum JAVA Memory (per worker)


#LOCAL SYSTEM SETTINGS
OPENSHA_ROOT = os.getenv('NZSHM22_OPENSHA_ROOT', "/Users/benchamberlain/gns/nzshm-runzi/")
OPENSHA_JRE = os.getenv('NZSHM22_OPENSHA_JRE', "/Library/Java/JavaVirtualMachines/jdk-11.0.12.jdk/Contents/Home/bin/java")
FATJAR = os.getenv('NZSHM22_FATJAR', None) or str(PurePath(OPENSHA_ROOT, "jar/nzshm-opensha-all.jar"))
WORK_PATH = os.getenv('NZSHM22_SCRIPT_WORK_PATH', PurePath(os.getcwd(), "tmp"))

CLUSTER_MODE = EnvMode[os.getenv('NZSHM22_SCRIPT_CLUSTER_MODE','LOCAL')] #Wase True/False now EnvMode: LOCAL, CLUSTER, AWS

#Inversion diagnostics settings
BUILD_PLOTS = os.getenv('NZSHM22_SCRIPT_BUILD_PLOTS', True)
REPORT_LEVEL = os.getenv('NZSHM22_SCRIPT_REPORT_LEVEL', "DEFAULT")

#Run java scripts or not - MOCK_MODE = True will not run java
MOCK_MODE = os.getenv('NZSHM22_SCRIPT_MOCK_MODE', False)

