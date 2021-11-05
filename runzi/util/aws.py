# Use this code snippet in your app.
# If you need more information about configurations or implementing the sample code, visit the AWS docs:   
# https://aws.amazon.com/developers/getting-started/python/

import boto3
import base64
import urllib.parse
from botocore.exceptions import ClientError
import json

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


def get_ecs_job_config(job_name, rupture_set_id, config, toshi_api_url, toshi_s3_url, time_minutes, memory, vcpu):

    assert vcpu in  [0.25, 0.5, 1, 2, 4]
    assert memory in [
        512, 1024, 2048, #value = 0.25
        1024, 2048, 3072, 4096, # value = 0.5
        2048, 3072, 4096, 5120, 6144, 7168,  8192, #value = 1
        4096, 5120, 6144, 7168, 8192, 9216, 10240, 11264, 12288, 13312, 14336, 15360, 16384, #value = 2
        8192, 9216, 10240, 11264, 12288, 13312, 14336, 15360, 16384, 17408,
        18432, 19456, 20480, 21504, 22528, 23552, 24576, 25600, 26624, 27648, 28672, 29696, 30720 #value = 4
    ]

    return {
        "jobName": job_name,
        "jobQueue": "BasicFargate_Q",
        "jobDefinition": "Fargate-runzi-opensha-JD",
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
                    "value": urllib.parse.quote(json.dumps(config))
                },
                {
                    "name": "TOSHI_RUPTURE_SET_ID",
                    "value": rupture_set_id
                },
                {
                    "name": "NZSHM22_SCRIPT_JVM_HEAP_MAX",
                    "value": str(int(memory/1000))
                },
                {
                    "name": "NZSHM22_TOSHI_S3_URL",
                    "value": toshi_s3_url
                },
                {
                    "name": "NZSHM22_TOSHI_API_URL",
                    "value": toshi_api_url
                },

            ]
        },
        "propagateTags": True,
        "timeout": {
            "attemptDurationSeconds": (time_minutes * 60) + 300
        }
    }


