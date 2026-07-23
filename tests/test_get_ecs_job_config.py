"""Tests for runzi.aws.get_ecs_job_config.

M2M auth config (NZSHM22_TOSHI_M2M_SECRET_ARN, NZSHM22_TOSHI_COGNITO_DOMAIN) is now
the responsibility of the AWS Batch job definition, not runzi. These tests confirm that
runzi never injects those vars into the container environment, so a local submitter's
Scientist credentials are not accidentally overridden by M2M config.
"""

import inspect
import json

import pytest

from runzi.arguments import (
    DEFAULT_JOB_DEFINITION,
    DEFAULT_JOB_QUEUE,
    EC2_EXPERIMENTAL_JOB_DEFINITION,
    EC2_JOB_DEFINITION,
    EC2_JOB_QUEUE,
    EXPERIMENTAL_JOB_DEFINITION,
    ComputeEnvironment,
    SubmissionArgs,
    TaskLanguage,
    TaskRuntimeArgs,
)
from runzi.aws import decompress_config, get_ecs_job_config
from runzi.aws.aws import BatchEnvironmentSetting, validate_ec2_resources, validate_fargate_resources


def _call_get_ecs_job_config(**overrides):
    """Call get_ecs_job_config with sensible defaults; override any param via kwargs."""
    kwargs = dict(
        job_name='test-job-1',
        container_task='run_task.sh',
        model_type=None,
        task_args=None,
        toshi_api_url='https://api.example.com/graphql',
        toshi_s3_url='https://s3.example.com',
        toshi_report_bucket='my-report-bucket',
        ths_rlz_db=None,
        ths_disagg_rlz_db=None,
        ecr_digest=None,
        task_module='runzi.tasks.oq_hazard.oq_hazard_task',
        time_minutes=60,
        memory=4096,
        vcpu=2,
        job_definition='BasicEC2-job-definition',
        job_queue='BasicEC2-job-queue',
        task_runtime_args=None,
    )
    kwargs.update(overrides)
    return get_ecs_job_config(**kwargs)  # type: ignore[arg-type]


def _env_names(config: dict) -> list[str]:
    """Extract env var names from a get_ecs_job_config result."""
    return [entry['name'] for entry in config['containerOverrides']['environment']]


class TestM2MNotForwarded:
    """M2M auth is now owned by the job definition, not runzi."""

    def test_m2m_secret_arn_not_in_container_env(self, mocker):
        """get_ecs_job_config must never inject NZSHM22_TOSHI_M2M_SECRET_ARN."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})

        result = _call_get_ecs_job_config()
        assert 'NZSHM22_TOSHI_M2M_SECRET_ARN' not in _env_names(result)

    def test_cognito_domain_not_in_container_env(self, mocker):
        """get_ecs_job_config must never inject NZSHM22_TOSHI_COGNITO_DOMAIN."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})

        result = _call_get_ecs_job_config()
        assert 'NZSHM22_TOSHI_COGNITO_DOMAIN' not in _env_names(result)

    def test_m2m_and_cognito_not_accepted_as_kwargs(self):
        """The function signature must not have m2m_secret_arn or cognito_domain params."""
        sig = inspect.signature(get_ecs_job_config)
        assert 'm2m_secret_arn' not in sig.parameters, (
            'get_ecs_job_config must not accept m2m_secret_arn; M2M config is now supplied by the Batch job definition'
        )
        assert 'cognito_domain' not in sig.parameters, (
            'get_ecs_job_config must not accept cognito_domain; M2M config is now supplied by the Batch job definition'
        )


class TestContainerEnvContents:
    """Sanity-check that the env entries we still own are present."""

    def test_required_env_vars_present(self, mocker):
        """Core env vars that runzi is responsible for must be in the container env."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})

        result = _call_get_ecs_job_config()
        names = _env_names(result)

        for required in [
            'TASK_CONFIG_JSON_QUOTED',
            'NZSHM22_TOSHI_API_URL',
            'NZSHM22_TOSHI_S3_URL',
            'NZSHM22_TOSHI_API_ENABLED',
            'AWS_DEFAULT_REGION',
        ]:
            assert required in names, f'{required} missing from container environment'

    def test_extra_env_appended(self, mocker):
        """Extra env entries (from SubmissionArgs.ecs_extra_env) are appended correctly."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        extra = [BatchEnvironmentSetting('MY_CUSTOM_VAR', 'hello')]

        result = _call_get_ecs_job_config(extra_env=extra)
        names = _env_names(result)
        assert 'MY_CUSTOM_VAR' in names
        entry = next(e for e in result['containerOverrides']['environment'] if e['name'] == 'MY_CUSTOM_VAR')
        assert entry['value'] == 'hello'

    def test_ths_rlz_db_and_disagg_rlz_db_are_independent(self, mocker):
        """NZSHM22_THS_RLZ_DB and NZSHM22_THS_DISAGG_RLZ_DB must be configurable independently."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(
            ths_rlz_db='s3://hazard-bucket/rlz',
            ths_disagg_rlz_db='s3://disagg-bucket/rlz',
        )
        env = {e['name']: e['value'] for e in result['containerOverrides']['environment']}
        assert env['NZSHM22_THS_RLZ_DB'] == 's3://hazard-bucket/rlz'
        assert env['NZSHM22_THS_DISAGG_RLZ_DB'] == 's3://disagg-bucket/rlz'

    def test_ths_disagg_rlz_db_defaults_to_working_path_when_none(self, mocker):
        """When ths_disagg_rlz_db is None, NZSHM22_THS_DISAGG_RLZ_DB gets the fallback path."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(ths_disagg_rlz_db=None)
        env = {e['name']: e['value'] for e in result['containerOverrides']['environment']}
        assert env['NZSHM22_THS_DISAGG_RLZ_DB'] == '/WORKING/THS_DISAGG_RLZ'


class TestValidateFargateResources:
    """validate_fargate_resources enforces the AWS Fargate vCPU/memory matrix."""

    @pytest.mark.parametrize(
        'vcpu, memory',
        [
            (0.25, 512),
            (0.5, 4096),
            (1, 2048),
            (2, 16384),
            (4, 30720),
            (8, 16384),
            (8, 32768),
            (16, 122880),
            (32, 61440),  # 60 GB
            (32, 122880),  # 120 GB
            (32, 249856),  # 244 GB
        ],
    )
    def test_valid_combinations_pass(self, vcpu, memory):
        validate_fargate_resources(vcpu, memory)  # must not raise

    def test_32_vcpu_rejects_non_discrete_memory(self):
        """Unlike 8/16 vCPU, 32 vCPU only allows the three discrete values, not a stepped range."""
        with pytest.raises(ValueError, match='not valid for 32 vCPU'):
            validate_fargate_resources(32, 90112)  # 88 GB, between 60 and 120 but not allowed

    def test_invalid_vcpu_raises(self):
        with pytest.raises(ValueError, match='not a valid Fargate vCPU'):
            validate_fargate_resources(6, 16384)

    def test_invalid_memory_for_vcpu_raises(self):
        # 30000 is not a valid 8-vCPU Fargate memory (must be a multiple of 4096 in 16384..61440).
        with pytest.raises(ValueError, match='not valid for 8 vCPU'):
            validate_fargate_resources(8, 30000)


class TestFargateValidationInJobConfig:
    """get_ecs_job_config validates vcpu/memory against the Fargate matrix by default
    (compute_environment defaults to FARGATE)."""

    def test_invalid_fargate_size_rejected(self, mocker):
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        with pytest.raises(ValueError):
            _call_get_ecs_job_config(job_definition=DEFAULT_JOB_DEFINITION, vcpu=8, memory=30000)

    def test_valid_fargate_size_accepted(self, mocker):
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(job_definition=DEFAULT_JOB_DEFINITION, vcpu=8, memory=32768)
        assert result['jobDefinition'] == DEFAULT_JOB_DEFINITION

    def test_invalid_size_rejected_regardless_of_job_definition_name(self, mocker):
        """Validation no longer keys off the job definition name; any job definition is checked."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        with pytest.raises(ValueError):
            _call_get_ecs_job_config(vcpu=8, memory=30000)  # BasicEC2-job-definition default name


class TestValidateEc2Resources:
    """validate_ec2_resources only does a light sanity check: EC2 sizing depends on the
    compute environment's instance types, which runzi can't know statically."""

    def test_normal_combination_passes(self):
        validate_ec2_resources(8, 30000)  # must not raise; not a valid Fargate size, fine on EC2

    def test_non_positive_memory_raises(self):
        with pytest.raises(ValueError, match='memory'):
            validate_ec2_resources(2, 0)

    def test_vcpu_below_one_raises(self):
        with pytest.raises(ValueError, match='vcpu'):
            validate_ec2_resources(0, 4096)


class TestComputeEnvironmentInJobConfig:
    """get_ecs_job_config branches its validation on compute_environment."""

    def test_ec2_accepts_off_fargate_matrix_size(self, mocker):
        """8 vCPU / 30000 MB is invalid for Fargate but fine for EC2 (light check only)."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(compute_environment=ComputeEnvironment.EC2, vcpu=8, memory=30000)
        assert result['containerOverrides']['resourceRequirements'] == [
            {"value": "30000", "type": "MEMORY"},
            {"value": "8", "type": "VCPU"},
        ]

    def test_fargate_still_rejects_off_matrix_size(self, mocker):
        """Same size is still rejected when compute_environment is FARGATE (the default)."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        with pytest.raises(ValueError):
            _call_get_ecs_job_config(compute_environment=ComputeEnvironment.FARGATE, vcpu=8, memory=30000)

    def test_string_compute_environment_is_coerced(self, mocker):
        """submission_arg_overrides uses setattr, which can leave a raw string instead of the enum."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(compute_environment='ec2', vcpu=8, memory=30000)
        assert result is not None


class TestEc2CanonicalNames:
    """The EC2 side has canonical Terraform-owned names mirroring Fargate (ADR-0008, #322)."""

    def test_ec2_names_distinct_from_fargate(self):
        assert EC2_JOB_DEFINITION == 'runzi-ec2-JD'
        assert EC2_EXPERIMENTAL_JOB_DEFINITION == 'runzi-ec2-experimental-JD'
        assert EC2_JOB_QUEUE == 'runzi-ec2-Q'
        # EC2 is an opt-in target, never the Fargate default.
        assert EC2_JOB_DEFINITION != DEFAULT_JOB_DEFINITION
        assert EC2_JOB_QUEUE != DEFAULT_JOB_QUEUE

    def test_canonical_ec2_target_builds_config(self, mocker):
        """Submitting to the canonical EC2 def/queue on the EC2 compute env builds a valid config."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(
            compute_environment=ComputeEnvironment.EC2,
            job_definition=EC2_JOB_DEFINITION,
            job_queue=EC2_JOB_QUEUE,
            vcpu=8,
            memory=30000,  # off the Fargate matrix; fine on EC2
        )
        assert result['jobDefinition'] == EC2_JOB_DEFINITION
        assert result['jobQueue'] == EC2_JOB_QUEUE


class TestCompression:
    """Large task configs are shipped LZMA+base64 compressed to stay under Batch's
    containerOverrides limit; AWS Batch caps containerOverrides at 8192 bytes."""

    def test_use_compression_round_trips(self, mocker):
        """With use_compression=True, TASK_CONFIG_JSON_QUOTED decodes back via decompress_config."""
        task_config = {"task_args": {"a": 1}, "task_runtime_args": {"b": 2}, "model_type": "X"}
        mocker.patch('runzi.aws.aws.get_task_config', return_value=task_config)

        result = _call_get_ecs_job_config(use_compression=True)
        env = {e['name']: e['value'] for e in result['containerOverrides']['environment']}
        decoded = json.loads(decompress_config(env['TASK_CONFIG_JSON_QUOTED']))
        assert decoded == task_config

    def test_use_compression_shrinks_large_config(self, mocker):
        """Compression should produce a smaller payload than url-quoting for a repetitive config."""
        large_task_config = {"items": [{"name": f"item-{i}", "value": "x" * 20} for i in range(50)]}
        mocker.patch('runzi.aws.aws.get_task_config', return_value=large_task_config)

        quoted_result = _call_get_ecs_job_config(use_compression=False)
        compressed_result = _call_get_ecs_job_config(use_compression=True)

        quoted_env = {e['name']: e['value'] for e in quoted_result['containerOverrides']['environment']}
        compressed_env = {e['name']: e['value'] for e in compressed_result['containerOverrides']['environment']}
        assert len(compressed_env['TASK_CONFIG_JSON_QUOTED']) < len(quoted_env['TASK_CONFIG_JSON_QUOTED'])

    def test_oversized_container_overrides_rejected(self, mocker):
        """get_ecs_job_config fails fast if containerOverrides would exceed Batch's 8192-byte limit,
        instead of letting submit_job fail with a cryptic AWS error."""
        # Not compressible (random-looking) and large enough that even compression can't save it.
        import random
        import string

        huge_task_config = {"blob": ''.join(random.choices(string.ascii_letters + string.digits, k=20000))}
        mocker.patch('runzi.aws.aws.get_task_config', return_value=huge_task_config)

        with pytest.raises(ValueError, match='8192'):
            _call_get_ecs_job_config(use_compression=True)


def _submission_args(**overrides) -> SubmissionArgs:
    """A minimal SubmissionArgs; override any field via kwargs."""
    kwargs = dict(
        task_language=TaskLanguage.PYTHON,
        ecs_max_job_time_min=10,
        ecs_memory=2048,
        ecs_vcpu=1,
    )
    kwargs.update(overrides)
    return SubmissionArgs(**kwargs)  # type: ignore[arg-type]


class TestSubmissionArgsComputeDefaults:
    """SubmissionArgs defaults to the prod Fargate job definition; queue/compute-env are derived."""

    def test_job_definition_defaults_to_prod_fargate(self):
        assert _submission_args().ecs_job_definition == DEFAULT_JOB_DEFINITION

    def test_queue_and_compute_are_unset_until_resolved(self):
        """The raw override inputs are None ('derive from the job definition')."""
        args = _submission_args()
        assert args.ecs_job_queue is None
        assert args.ecs_compute_environment is None

    def test_default_resolves_to_fargate(self):
        args = _submission_args()
        assert args.resolved_job_queue == DEFAULT_JOB_QUEUE
        assert args.resolved_compute_environment == ComputeEnvironment.FARGATE


class TestBatchTargetResolution:
    """The queue + compute-environment type derive from the chosen job definition, so a user picks
    only the job definition (ADR-0008 addendum). Explicit overrides still win."""

    @pytest.mark.parametrize(
        'job_definition, expected_queue, expected_compute',
        [
            (DEFAULT_JOB_DEFINITION, DEFAULT_JOB_QUEUE, ComputeEnvironment.FARGATE),
            (EXPERIMENTAL_JOB_DEFINITION, DEFAULT_JOB_QUEUE, ComputeEnvironment.FARGATE),
            (EC2_JOB_DEFINITION, EC2_JOB_QUEUE, ComputeEnvironment.EC2),
            (EC2_EXPERIMENTAL_JOB_DEFINITION, EC2_JOB_QUEUE, ComputeEnvironment.EC2),
        ],
    )
    def test_canonical_job_definition_selects_its_target(self, job_definition, expected_queue, expected_compute):
        args = _submission_args(ecs_job_definition=job_definition)
        assert args.resolved_job_queue == expected_queue
        assert args.resolved_compute_environment == expected_compute

    def test_picking_ec2_job_definition_alone_targets_ec2(self):
        """The friction fix: set only the job definition, queue + type follow."""
        args = _submission_args(ecs_job_definition=EC2_JOB_DEFINITION)
        assert args.resolved_job_queue == EC2_JOB_QUEUE
        assert args.resolved_compute_environment == ComputeEnvironment.EC2

    def test_explicit_queue_override_is_respected(self):
        args = _submission_args(ecs_job_definition=EC2_JOB_DEFINITION, ecs_job_queue='my-special-Q')
        assert args.resolved_job_queue == 'my-special-Q'

    def test_explicit_compute_override_is_respected(self):
        args = _submission_args(
            ecs_job_definition=DEFAULT_JOB_DEFINITION, ecs_compute_environment=ComputeEnvironment.EC2
        )
        assert args.resolved_compute_environment == ComputeEnvironment.EC2

    def test_unknown_job_definition_falls_back_to_fargate(self):
        args = _submission_args(ecs_job_definition='some-custom-JD')
        assert args.resolved_job_queue == DEFAULT_JOB_QUEUE
        assert args.resolved_compute_environment == ComputeEnvironment.FARGATE

    def test_derivation_follows_post_construction_override(self):
        """Mirrors JobRunner.set_submission_args, which applies overrides by assignment after
        construction: the resolved properties must reflect the new job definition (never stale)."""
        args = _submission_args()  # default prod Fargate JD
        assert args.resolved_job_queue == DEFAULT_JOB_QUEUE
        args.ecs_job_definition = EC2_JOB_DEFINITION
        assert args.resolved_job_queue == EC2_JOB_QUEUE
        assert args.resolved_compute_environment == ComputeEnvironment.EC2


class TestSubmissionArgsNotShipped:
    """SubmissionArgs is submitter-only; only TaskRuntimeArgs crosses to the worker (ADR-0009)."""

    def test_submission_args_has_no_runtime_fields(self):
        fields = set(SubmissionArgs.model_fields)
        assert {'general_task_id', 'task_count', 'use_api'} & fields == set()

    def test_runtime_args_has_no_submission_fields(self):
        fields = set(TaskRuntimeArgs.model_fields)
        assert {
            'ecs_job_queue',
            'ecs_compute_environment',
            'ecs_job_definition',
            'ecs_memory',
            'ecs_vcpu',
            'ecs_max_job_time_min',
            'task_language',
            'ecs_extra_env',
        } & fields == set()


class TestTaskRuntimeArgsSerialization:
    """The only args model shipped to the worker; it must round-trip through the config the worker
    rebuilds it from (regression: the old single-class model shipped submission fields the worker
    then had to validate)."""

    def test_round_trips_through_worker_serialization(self):
        """Reproduces the worker path: model_dump(mode='json') then TaskRuntimeArgs(**dumped)."""
        args = TaskRuntimeArgs(general_task_id='GT-1', task_count=3, use_api=True, num_cores=16)
        rebuilt = TaskRuntimeArgs(**args.model_dump(mode='json'))
        assert rebuilt == args

    def test_carries_no_submission_keys(self):
        dumped = TaskRuntimeArgs(use_api=True).model_dump(mode='json')
        assert 'ecs_job_queue' not in dumped
        assert 'ecs_compute_environment' not in dumped
        assert set(dumped) == {'general_task_id', 'task_count', 'use_api', 'num_cores'}
