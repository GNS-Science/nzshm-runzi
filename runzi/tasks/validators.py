"""Shared validators for runzi task Args models."""

from pathlib import Path
from typing import Any

from pydantic import ValidationInfo


def all_or_none(params: list) -> bool:
    """Checks that either all or none of the parameters have been set (non-None).

    Args:
        params: List of values to check. Each element is tested for None.

    Returns:
        True if all elements are None or all are non-None; False if mixed.
    """
    is_none = [param is None for param in params]
    if (not all(is_none)) and (any(is_none)):
        return False
    return True


def exactly_one(params: list) -> bool:
    """Checks that exactly one of the parameters has been set (non-None).

    Args:
        params: List of values to check. Each element is tested for None.

    Returns:
        True if exactly one element is non-None; False otherwise.
    """
    return sum(p is not None for p in params) == 1


def at_most_one(params: list) -> bool:
    """Checks that no more than one of the parameters has been set (non-None).

    Args:
        params: List of values to check. Each element is tested for None.

    Returns:
        True if zero or one element is non-None; False if two or more are set.
    """
    return sum(p is not None for p in params) <= 1


def resolve_path(value: Any, info: ValidationInfo) -> Any:
    """Resolve a Path field to an absolute path using the 'base_path' validation context.

    Intended for use as an @field_validator(mode='after') on Path-typed fields.
    If the path is relative and a base_path is present in the validation context,
    the path is resolved relative to base_path.

    Args:
        value: The field value to validate. Non-Path values are returned unchanged.
        info: Pydantic ValidationInfo. If info.context is a dict containing
            'base_path', relative paths are resolved against it.

    Returns:
        The resolved absolute Path if value is a Path, otherwise value unchanged.

    Raises:
        ValueError: If value is a Path and the resolved path does not exist.
    """
    if isinstance(value, Path):
        file_path = value
        if not file_path.is_absolute():
            if isinstance(info.context, dict):
                base_path = info.context.get("base_path")
                if base_path is not None:
                    file_path = (Path(base_path) / file_path).resolve()
        if not file_path.exists():
            raise ValueError(f"file {value} does not exist")
        return file_path
    return value
