# Use this code snippet in your app.
# If you need more information about configurations or implementing the sample code, visit the AWS docs:   
# https://aws.amazon.com/developers/getting-started/python/

import boto3
import base64
import io
import zipfile

import urllib.parse
from botocore.exceptions import ClientError
import json
import collections
from typing import List

BatchEnvironmentSetting = collections.namedtuple('BatchEnvironmentSetting', 'name value')

def get_secret(secret_name, region_name):

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            return json.loads(get_secret_value_response['SecretString'])
        else:
            return base64.b64decode(get_secret_value_response['SecretBinary'])

def compress_config(config):
    """Use LZMA compression to pack this config into a much smaller string"""
    compressed = io.BytesIO()
    with zipfile.ZipFile(compressed, 'w', compression=zipfile.ZIP_LZMA ) as zf:
        zf.writestr('0', config)
        zf.close()
    compressed.seek(0)
    b64 = base64.b64encode(compressed.read())
    return b64.decode('ascii')

def decompress_config(compressed):
    """decompres an LZMA compressed config."""
    base64_bytes = compressed.encode('ascii')
    message_bytes = base64.b64decode(base64_bytes)

    ## Decompression
    zfout = zipfile.ZipFile(io.BytesIO(message_bytes))
    msg_out = io.BytesIO(zfout.read('0'))
    msg_out.seek(0)
    return msg_out.read().decode('ascii')

def get_ecs_job_config(job_name, toshi_file_id, config, toshi_api_url, toshi_s3_url,
    toshi_report_bucket, task_module, time_minutes, memory, vcpu,
    job_definition="Fargate-runzi-opensha-JD",
    job_queue="BasicFargate_Q",
    extra_env: List[BatchEnvironmentSetting] = None, use_compression = False):

    if "Fargate" in job_definition:
        assert vcpu in  [0.25, 0.5, 1, 2, 4]
        assert memory in [
            512, 1024, 2048, #value = 0.25
            1024, 2048, 3072, 4096, # value = 0.5
            2048, 3072, 4096, 5120, 6144, 7168,  8192, #value = 1
            4096, 5120, 6144, 7168, 8192, 9216, 10240, 11264, 12288, 13312, 14336, 15360, 16384, #value = 2
            8192, 9216, 10240, 11264, 12288, 13312, 14336, 15360, 16384, 17408,
            18432, 19456, 20480, 21504, 22528, 23552, 24576, 25600, 26624, 27648, 28672, 29696, 30720, #value = 4
            ]
    #     job_queue = "BasicFargate_Q"
    # else:
    #     job_queue = "BigLeverOnDemandEC2-job-queue" #"getting-started-jun7" #"BiggerLeverQueue"

    config = {
        "jobName": job_name,
        "jobQueue": job_queue,
        "jobDefinition": job_definition,
        "containerOverrides": {
            "command": [
                "-s",
                "/app/container_task.sh"
            ],
            "resourceRequirements": [
                {
                    "value": str(memory),
                    "type": "MEMORY"
                },
                {
                    "value": str(vcpu),
                    "type": "VCPU"
                }
            ],
            "environment": [
                {
                    "name": "TASK_CONFIG_JSON_QUOTED",
                    "value": compress_config(json.dumps(config)) if use_compression else urllib.parse.quote(json.dumps(config))
                },
                {
                    "name": "NZSHM22_SCRIPT_JVM_HEAP_MAX",
                    "value": str(int(memory/1000)-2)
                },
                {
                    "name": "NZSHM22_AWS_JAVA_THREADS",
                    "value": str(int(vcpu))
                },
                {
                    "name": "NZSHM22_TOSHI_S3_URL",
                    "value": toshi_s3_url
                },
                {
                    "name": "NZSHM22_TOSHI_API_URL",
                    "value": toshi_api_url
                },
                {
                    "name": "NZSHM22_S3_REPORT_BUCKET",
                    "value": toshi_report_bucket
                },
                {
                    "name": "TOSHI_FILE_ID",
                    "value": toshi_file_id
                },
                {
                    "name": "PYTHON_PREP_MODULE",
                    "value": 'runzi.execute.prepare_inputs'
                },
                {
                    "name": "PYTHON_TASK_MODULE",
                    "value": task_module
                }
            ]
        },
        "propagateTags": True,
        "timeout": {
            "attemptDurationSeconds": (time_minutes * 60) + 1800
        }
    }

    if extra_env:
        for ex in extra_env:
            config['containerOverrides']['environment'].append(dict(name=ex.name, value=ex.value))

    return config