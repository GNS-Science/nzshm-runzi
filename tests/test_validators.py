"""Tests for runzi/tasks/validators.py."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from runzi.tasks.validators import all_or_none, resolve_path


class TestAllOrNone:
    def test_all_none(self):
        assert all_or_none([None, None, None]) is True

    def test_all_set(self):
        assert all_or_none([1, 2, 3]) is True

    def test_partial_none(self):
        assert all_or_none([1, None, 3]) is False

    def test_first_none(self):
        assert all_or_none([None, 2, 3]) is False

    def test_last_none(self):
        assert all_or_none([1, 2, None]) is False

    def test_single_none(self):
        assert all_or_none([None]) is True

    def test_single_set(self):
        assert all_or_none([42]) is True


class TestResolvePath:
    def _make_info(self, context=None):
        info = MagicMock()
        info.context = context
        return info

    def test_non_path_value_returned_unchanged(self):
        info = self._make_info()
        assert resolve_path("not_a_path", info) == "not_a_path"
        assert resolve_path(None, info) is None
        assert resolve_path(42, info) == 42

    def test_absolute_path_existing(self):
        with tempfile.NamedTemporaryFile() as f:
            p = Path(f.name)
            info = self._make_info()
            result = resolve_path(p, info)
            assert result == p

    def test_absolute_path_nonexistent_raises(self):
        p = Path('/nonexistent/path/to/file.txt')
        info = self._make_info()
        with pytest.raises(ValueError, match='does not exist'):
            resolve_path(p, info)

    def test_relative_path_with_base_path_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # create a file in tmpdir
            target = Path(tmpdir) / 'myfile.txt'
            target.write_text('hello')
            info = self._make_info(context={'base_path': tmpdir})
            result = resolve_path(Path('myfile.txt'), info)
            assert result == target.resolve()

    def test_relative_path_without_context_raises(self):
        info = self._make_info(context=None)
        with pytest.raises(ValueError, match='does not exist'):
            resolve_path(Path('nonexistent_relative_file.txt'), info)

    def test_relative_path_with_context_missing_base_path_raises(self):
        info = self._make_info(context={'other_key': 'value'})
        with pytest.raises(ValueError, match='does not exist'):
            resolve_path(Path('nonexistent_relative_file.txt'), info)

    def test_relative_path_with_base_path_nonexistent_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            info = self._make_info(context={'base_path': tmpdir})
            with pytest.raises(ValueError, match='does not exist'):
                resolve_path(Path('missing_file.txt'), info)
