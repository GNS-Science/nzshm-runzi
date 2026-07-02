from typing import Protocol

from runzi.arguments import SubmissionArgs


class ModuleWithDefaultSubmissionArgs(Protocol):
    """Protocol for task modules that provide default submission arguments."""

    default_submission_args: SubmissionArgs
    __name__: str
