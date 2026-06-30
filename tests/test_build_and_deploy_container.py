"""Tests for runzi.cli.build_and_deploy_container.

The Batch job definitions are Terraform-owned and track stable image *tags*, so publishing no
longer registers a job definition. `docker-build` moves the :experimental tag onto a freshly-pushed
image; `promote` moves the :prod tag onto an already-published manifest. These tests pin that
behaviour and guard against the retired :latest tag / job-definition re-registration creeping back.
"""

import pytest

import runzi.cli.build_and_deploy_container as bdc
from runzi.cli.build_and_deploy_container import retag_image, tag_and_push_image


def _push_uris(mock_run):
    """Image URIs passed to `docker push` across all recorded subprocess.run calls."""
    return [call.args[0][2] for call in mock_run.call_args_list if call.args[0][:2] == ["docker", "push"]]


def test_tag_and_push_targets_version_and_experimental_not_latest(mocker):
    """The build pushes the immutable version tag and :experimental, and never :latest."""
    mock_run = mocker.patch("runzi.cli.build_and_deploy_container.subprocess.run")
    mock_run.return_value.stdout = "[461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi@sha256:abcd]\n"

    image_uri, digest = tag_and_push_image(
        "nzshm22/runzi", "461564345538", "us-east-1", "abc1234", "3.11", "TAG", "3.19"
    )

    pushed = _push_uris(mock_run)
    assert any(uri.endswith(":experimental") for uri in pushed), pushed
    assert any("runzi-abc1234_py3.11_opensha-TAG_oq-3.19" in uri for uri in pushed), pushed
    assert not any(uri.endswith(":latest") for uri in pushed), pushed
    assert image_uri.endswith("runzi-abc1234_py3.11_opensha-TAG_oq-3.19")
    assert digest == "sha256:abcd"


def test_tag_and_push_does_not_register_a_job_definition(mocker):
    """Publishing must not touch Batch — no job-definition registration from the CLI."""
    mocker.patch(
        "runzi.cli.build_and_deploy_container.subprocess.run"
    ).return_value.stdout = "[nzshm22/runzi@sha256:abcd]\n"
    mock_boto = mocker.patch("boto3.client")

    tag_and_push_image("nzshm22/runzi", "461564345538", "us-east-1", "abc1234", "3.11", "TAG", "3.19")

    mock_boto.assert_not_called()


def test_update_job_definition_is_removed():
    """The digest-pinned re-register helper is gone (job defs are Terraform-owned, tag-tracked)."""
    assert not hasattr(bdc, "update_job_definition")


def test_retag_image_moves_target_tag_onto_source_manifest(mocker):
    """promote retags inside ECR: read the source manifest, put it under the target tag."""
    mock_ecr = mocker.Mock()
    mock_ecr.batch_get_image.return_value = {
        "images": [{"imageManifest": "MANIFEST-JSON", "imageId": {"imageDigest": "sha256:dead"}}]
    }
    mocker.patch("boto3.client", return_value=mock_ecr)

    digest = retag_image("nzshm22/runzi", "us-east-1", "experimental", "prod")

    mock_ecr.batch_get_image.assert_called_once_with(
        repositoryName="nzshm22/runzi", imageIds=[{"imageTag": "experimental"}]
    )
    _, kwargs = mock_ecr.put_image.call_args
    assert kwargs["repositoryName"] == "nzshm22/runzi"
    assert kwargs["imageManifest"] == "MANIFEST-JSON"
    assert kwargs["imageTag"] == "prod"
    assert digest == "sha256:dead"


def test_retag_image_is_a_noop_when_target_already_points_at_source(mocker):
    """Re-promoting the same digest is harmless: ImageAlreadyExistsException is swallowed."""

    class ImageAlreadyExistsException(Exception):
        pass

    mock_ecr = mocker.Mock()
    mock_ecr.exceptions.ImageAlreadyExistsException = ImageAlreadyExistsException
    mock_ecr.batch_get_image.return_value = {
        "images": [{"imageManifest": "M", "imageId": {"imageDigest": "sha256:dead"}}]
    }
    mock_ecr.put_image.side_effect = ImageAlreadyExistsException()
    mocker.patch("boto3.client", return_value=mock_ecr)

    assert retag_image("nzshm22/runzi", "us-east-1", "prod", "prod") == "sha256:dead"


def test_retag_image_errors_when_source_tag_missing(mocker):
    """Promoting a tag that doesn't exist is a hard error, not a silent prod change."""
    mock_ecr = mocker.Mock()
    mock_ecr.batch_get_image.return_value = {"images": []}
    mocker.patch("boto3.client", return_value=mock_ecr)

    with pytest.raises(RuntimeError, match="No image tagged 'nope'"):
        retag_image("nzshm22/runzi", "us-east-1", "nope", "prod")
