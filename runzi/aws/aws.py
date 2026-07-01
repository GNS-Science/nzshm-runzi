# Use this code snippet in your app.
# If you need more information about configurations or implementing the sample code, visit the AWS docs:
# https://aws.amazon.com/developers/getting-started/python/

import base64
import collections
import io
import json
import logging
import os
import urllib.parse
import zipfile
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from runzi.automation.task_config import get_task_config
from runzi.automation.toshi_api.general_task import ModelType
from runzi.aws.session import get_session

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from runzi.arguments import ComputeEnvironment, TaskRuntimeArgs

BatchEnvironmentSetting = collections.namedtuple('BatchEnvironmentSetting', 'name value')

# AWS Batch SubmitJob hard limit on the total size of containerOverrides.
MAX_CONTAINER_OVERRIDES_BYTES = 8192


def _fargate_memory_values(min_mb: int, max_mb: int, step_mb: int) -> tuple[int, ...]:
    return tuple(range(min_mb, max_mb + 1, step_mb))


# Valid AWS Fargate task vCPU/memory(MB) combinations, encoded from the AWS docs table
# "Fargate task CPU and memory":
# https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-defs.html#fargate-tasks-size
# AWS only ever expands this matrix, so a stale copy fails closed (rejects a newly-valid combo)
# rather than accepting an invalid one; submit_job is the ultimate validator. To refresh, update
# the ranges below and bump the marker.
# last verified: 2026-06
FARGATE_VCPU_MEMORY_MB: dict[float, tuple[int, ...]] = {
    0.25: (512, 1024, 2048),
    0.5: _fargate_memory_values(1024, 4096, 1024),
    1: _fargate_memory_values(2048, 8192, 1024),
    2: _fargate_memory_values(4096, 16384, 1024),
    4: _fargate_memory_values(8192, 30720, 1024),
    8: _fargate_memory_values(16384, 61440, 4096),
    16: _fargate_memory_values(32768, 122880, 8192),
    32: (61440, 122880, 249856),  # 60 GB, 120 GB, 244 GB — discrete, not a stepped range
}


def validate_fargate_resources(vcpu: float, memory: int) -> None:
    """Validate a vCPU/memory pair against the AWS Fargate task size matrix.

    Args:
        vcpu: requested vCPU (must be a Fargate-supported value).
        memory: requested memory in MB.

    Raises:
        ValueError: if vcpu is not a supported Fargate value, or memory is not a valid
            amount for that vcpu.
    """
    if vcpu not in FARGATE_VCPU_MEMORY_MB:
        raise ValueError(
            f"vcpu={vcpu} is not a valid Fargate vCPU value; choose one of {sorted(FARGATE_VCPU_MEMORY_MB)}"
        )
    valid_memory = FARGATE_VCPU_MEMORY_MB[vcpu]
    if memory not in valid_memory:
        raise ValueError(
            f"memory={memory} MB is not valid for {vcpu} vCPU on Fargate; valid values are "
            f"{valid_memory[0]}-{valid_memory[-1]} MB (allowed: {list(valid_memory)})"
        )


def validate_ec2_resources(vcpu: float, memory: int) -> None:
    """Light sanity check for an EC2 vCPU/memory pair.

    Unlike Fargate, EC2 has no fixed CPU/memory matrix: the values are minimums that the Batch
    scheduler bin-packs onto whatever instance types the compute environment offers, so runzi
    can't validate them against a static table. This only catches obviously-wrong values; the
    scheduler is the real arbiter. A request that's too large for any instance in the compute
    environment won't raise here — it will sit in RUNNABLE forever instead, so size EC2 jobs
    with some margin below your largest instance's allocatable memory.

    Args:
        vcpu: requested vCPU; must be a positive integer.
        memory: requested memory in MB; must be positive.

    Raises:
        ValueError: if vcpu is not a positive integer, or memory is not positive.
    """
    if vcpu < 1 or vcpu != int(vcpu):
        raise ValueError(f"vcpu={vcpu} is not valid for EC2; must be a positive integer")
    if memory <= 0:
        raise ValueError(f"memory={memory} MB is not valid for EC2; must be positive")


def get_secret(secret_name, region_name):

    # Create a Secrets Manager client
    client = get_session().client(service_name='secretsmanager', region_name=region_name)

    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
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


def resolve_job_definition_digest(job_definition: str, region_name: str | None = None) -> str | None:
    """Resolve the concrete image digest the named job definition currently points at.

    The Terraform-owned job definitions track a floating ECR tag (``:prod`` / ``:experimental``), so
    the digest that actually runs changes as images are published or promoted. Resolving it at
    submit time keeps toshi provenance (``NZSHM22_RUNZI_ECR_DIGEST``) honest about which image a job
    ran. Returns ``None`` if it can't be resolved (e.g. no AWS access, missing tag) so the caller can
    fall back to a configured digest.
    """
    region_name = region_name or os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
    try:
        session = get_session()
        batch_client = session.client(service_name='batch', region_name=region_name)
        response = batch_client.describe_job_definitions(
            jobDefinitionName=job_definition, status='ACTIVE', maxResults=1
        )
        job_defs = response.get('jobDefinitions')
        if not job_defs:
            return None

        image = job_defs[0]['containerProperties']['image']  # e.g. <registry>/nzshm22/runzi:prod
        ref = image.split('/', 1)[1] if '/' in image else image
        if '@' in ref:
            return ref.split('@', 1)[1]  # job definition already pins a digest

        repository, _, tag = ref.rpartition(':')
        if not tag:
            return None

        ecr_client = session.client(service_name='ecr', region_name=region_name)
        images = ecr_client.batch_get_image(repositoryName=repository, imageIds=[{'imageTag': tag}]).get('images', [])
        if not images:
            return None
        return images[0]['imageId'].get('imageDigest')
    except Exception as exc:  # noqa: BLE001 - provenance resolution must never block submission
        log.warning("Could not resolve image digest for job definition '%s': %s", job_definition, exc)
        return None


def compress_config(config):
    """Use LZMA compression to pack this config into a much smaller string"""
    compressed = io.BytesIO()
    with zipfile.ZipFile(compressed, 'w', compression=zipfile.ZIP_LZMA) as zf:
        zf.writestr('0', config)
        zf.close()
    compressed.seek(0)
    b64 = base64.b64encode(compressed.read())
    return b64.decode('ascii')


def decompress_config(compressed):
    """decompres an LZMA compressed config."""
    base64_bytes = compressed.encode('ascii')
    message_bytes = base64.b64decode(base64_bytes)

    # Decompression
    zfout = zipfile.ZipFile(io.BytesIO(message_bytes))
    msg_out = io.BytesIO(zfout.read('0'))
    msg_out.seek(0)
    return msg_out.read().decode('ascii')


def get_ecs_job_config(
    job_name: str,
    container_task: str,
    model_type: 'ModelType',
    task_args: 'BaseModel',
    task_runtime_args: 'TaskRuntimeArgs',
    toshi_api_url: str,
    toshi_s3_url: str,
    toshi_report_bucket: str,
    ths_rlz_db: str | None,
    ths_disagg_rlz_db: str | None,
    ecr_digest: str | None,
    task_module: str,
    time_minutes: int,
    memory: int,
    vcpu: int,
    job_definition: str,
    job_queue: str,
    extra_env: list[BatchEnvironmentSetting] | None = None,
    use_compression=False,
    compute_environment: 'ComputeEnvironment | str' = 'fargate',
):

    ths_rlz_db = ths_rlz_db or '/WORKING/THS_RLZ'
    ths_disagg_rlz_db = ths_disagg_rlz_db or '/WORKING/THS_DISAGG_RLZ'
    ecr_digest = ecr_digest or "sha256:NOT_SET"
    task_config = get_task_config(task_args, task_runtime_args, model_type)
    # compute_environment may be the ComputeEnvironment enum or a raw string (submission_arg_overrides
    # applies config-file overrides via setattr, which bypasses pydantic coercion).
    compute_target = getattr(compute_environment, 'value', compute_environment)
    if compute_target == 'ec2':
        validate_ec2_resources(vcpu, memory)
    else:
        validate_fargate_resources(vcpu, memory)

    config: dict[str, Any] = {
        "jobName": job_name,
        "jobQueue": job_queue,
        "jobDefinition": job_definition,
        "containerOverrides": {
            "command": ["-s", f"/usr/local/bin/{container_task}"],
            "resourceRequirements": [{"value": str(memory), "type": "MEMORY"}, {"value": str(vcpu), "type": "VCPU"}],
            "environment": [
                {
                    "name": "TASK_CONFIG_JSON_QUOTED",
                    "value": (
                        compress_config(json.dumps(task_config))
                        if use_compression
                        else urllib.parse.quote(json.dumps(task_config))
                    ),
                },
                {"name": "NZSHM22_SCRIPT_JVM_HEAP_MAX", "value": str(int(memory / 1000) - 2)},
                {"name": "NZSHM22_AWS_JAVA_THREADS", "value": str(int(vcpu))},
                {"name": "NZSHM22_TOSHI_S3_URL", "value": toshi_s3_url},
                {"name": "NZSHM22_TOSHI_API_URL", "value": toshi_api_url},
                {"name": "NZSHM22_TOSHI_API_ENABLED", "value": "1"},
                {"name": "NZSHM22_S3_REPORT_BUCKET", "value": toshi_report_bucket},
                {"name": "NZSHM22_RUNZI_ECR_DIGEST", "value": ecr_digest},
                {"name": "NZSHM22_THS_RLZ_DB", "value": ths_rlz_db},
                {"name": "NZSHM22_THS_DISAGG_RLZ_DB", "value": ths_disagg_rlz_db},
                {"name": "PYTHON_TASK_MODULE", "value": task_module},
                {"name": "AWS_DEFAULT_REGION", "value": os.getenv("AWS_DEFAULT_REGION", "us-east-1")},
            ],
        },
        "propagateTags": True,
        "timeout": {"attemptDurationSeconds": (time_minutes * 60) + (5 * 60)},
    }

    if extra_env:
        for ex in extra_env:
            config['containerOverrides']['environment'].append(dict(name=ex.name, value=ex.value))

    overrides_size = len(json.dumps(config['containerOverrides']))
    if overrides_size > MAX_CONTAINER_OVERRIDES_BYTES:
        raise ValueError(
            f"containerOverrides is {overrides_size} bytes, which exceeds AWS Batch's "
            f"{MAX_CONTAINER_OVERRIDES_BYTES}-byte limit even after compression. The task config is too "
            "large to ship inline; it needs to be staged externally (e.g. S3) and referenced instead."
        )

    return config
