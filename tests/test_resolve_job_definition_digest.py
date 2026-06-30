"""Tests for runzi.aws.aws.resolve_job_definition_digest.

The Terraform-owned job definitions track a floating image tag (:prod / :experimental), so the
digest a job actually runs has to be resolved at submit time for honest toshi provenance. The
resolver describes the job definition to find its image reference, then resolves that tag to a
concrete digest in ECR — and must degrade to None (never raise) so it can't block submission.
"""

from runzi.aws import resolve_job_definition_digest


def _session_with(batch_response, ecr_response, mocker):
    """Patch get_session so .client('batch') / .client('ecr') return canned responses."""
    batch_client = mocker.Mock()
    batch_client.describe_job_definitions.return_value = batch_response
    ecr_client = mocker.Mock()
    ecr_client.batch_get_image.return_value = ecr_response

    session = mocker.Mock()
    session.client.side_effect = lambda service_name, **_: {
        'batch': batch_client,
        'ecr': ecr_client,
    }[service_name]
    mocker.patch('runzi.aws.aws.get_session', return_value=session)
    return batch_client, ecr_client


def test_resolves_tag_to_digest(mocker):
    """A tag-tracking job definition resolves to the digest its tag currently points at."""
    batch_client, ecr_client = _session_with(
        {
            'jobDefinitions': [
                {'containerProperties': {'image': '4615.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:prod'}}
            ]
        },
        {'images': [{'imageId': {'imageDigest': 'sha256:beef'}}]},
        mocker,
    )

    assert resolve_job_definition_digest('runzi-fargate-JD', 'us-east-1') == 'sha256:beef'

    batch_client.describe_job_definitions.assert_called_once_with(
        jobDefinitionName='runzi-fargate-JD', status='ACTIVE', maxResults=1
    )
    _, kwargs = ecr_client.batch_get_image.call_args
    assert kwargs['repositoryName'] == 'nzshm22/runzi'
    assert kwargs['imageIds'] == [{'imageTag': 'prod'}]


def test_returns_pinned_digest_without_ecr_call(mocker):
    """If a job definition already pins a digest, return it directly (no ECR lookup)."""
    _, ecr_client = _session_with(
        {
            'jobDefinitions': [
                {'containerProperties': {'image': '4615.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi@sha256:pin'}}
            ]
        },
        {'images': []},
        mocker,
    )

    assert resolve_job_definition_digest('runzi-fargate-JD') == 'sha256:pin'
    ecr_client.batch_get_image.assert_not_called()


def test_returns_none_when_job_definition_missing(mocker):
    """No active job definition → None (caller falls back to the configured digest)."""
    _session_with({'jobDefinitions': []}, {'images': []}, mocker)
    assert resolve_job_definition_digest('nope') is None


def test_never_raises_on_aws_error(mocker):
    """Provenance resolution must never block submission — exceptions become None."""
    session = mocker.Mock()
    session.client.side_effect = RuntimeError('no credentials')
    mocker.patch('runzi.aws.aws.get_session', return_value=session)

    assert resolve_job_definition_digest('runzi-fargate-JD') is None
