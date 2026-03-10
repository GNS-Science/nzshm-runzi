from typing import Protocol

from runzi.arguments import SystemArgs


class ModuleWithDefaultSysArgs(Protocol):
    """Protocol for task modules that provide default system arguments."""

    default_system_args: SystemArgs
    __name__: str
