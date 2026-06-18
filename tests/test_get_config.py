"""Tests for runzi.tasks.get_config.get_config.

AWS Batch caps containerOverrides at 8192 bytes, so large task configs are shipped
LZMA+base64 compressed (see runzi.aws.compress_config) instead of URL-quoted. get_config
must be able to decode either form, plus the LOCAL/CLUSTER file-path form.
"""

import json

import pytest

from runzi.aws import compress_config
from runzi.tasks.get_config import get_config


def test_decodes_url_quoted_json(monkeypatch):
    """The existing plain url-quoted JSON form still works."""
    config = {"task_args": {"a": 1}, "task_system_args": {"b": 2}, "model_type": "X"}
    quoted = __import__('urllib.parse', fromlist=['quote']).quote(json.dumps(config))
    monkeypatch.setattr('sys.argv', ['prog', quoted])

    assert get_config() == config


def test_decodes_compressed_json(monkeypatch):
    """A compressed (LZMA+base64) payload, as produced for AWS Fargate jobs, decodes back."""
    config = {"task_args": {"a": 1}, "task_system_args": {"b": 2}, "model_type": "X"}
    compressed = compress_config(json.dumps(config))
    monkeypatch.setattr('sys.argv', ['prog', compressed])

    assert get_config() == config


def test_reads_from_file_when_not_json(monkeypatch, tmp_path):
    """LOCAL/CLUSTER mode passes a path to a JSON file instead of an inline string."""
    config = {"task_args": {"a": 1}, "task_system_args": {"b": 2}, "model_type": "X"}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['prog', str(config_file)])

    assert get_config() == config


def test_missing_file_raises(monkeypatch):
    """A value that is neither quoted JSON, compressed JSON, nor an existing file should error."""
    monkeypatch.setattr('sys.argv', ['prog', '/no/such/file/here.json'])

    with pytest.raises(FileNotFoundError):
        get_config()
