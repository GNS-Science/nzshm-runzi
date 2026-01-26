#!python3

"""
Wrapper script that produces an Python job that can be run either locally or
to a cluster using PBS

The job is responsible for configuring and executing the python script

 The job is either a bash script (for local machine) or
 a PBS script for the cluster environment
"""
import json
import os
from pathlib import Path, PurePath
from types import ModuleType
from typing import Optional

from pydantic import BaseModel

from runzi.automation.scaling.task_config import get_task_config

from .local_config import EnvMode


class PythonTaskFactory:

    def __init__(
        self,
        working_path: Path | PurePath | str,
        python_script_module: ModuleType,
        task_config_path: Optional[Path | PurePath | str] = None,
        python: str = 'python3',
    ):

        self._config_path = Path(task_config_path or Path.cwd())
        self._python_script = os.path.abspath(python_script_module.__file__)  # type: ignore
        self._working_path = working_path
        self._python = str(python)
        self._next_task = 1

    @classmethod
    def create(cls, **kwargs) -> 'PythonTaskFactory':
        return cls(
            kwargs['working_path'],
            kwargs['python_script_module'],
            task_config_path=kwargs.get('task_config_path'),
            python=kwargs.get('python', 'python3'),
        )

    def get_next_port(self) -> int:
        return self._next_task

    def write_task_config(self, task_arguments: BaseModel, task_system_args: BaseModel):
        fname = self._config_path / f"config.{self._next_task}.json"
        task_config = get_task_config(task_arguments, task_system_args)
        fname.write_text(json.dumps(task_config, indent=4), encoding='utf-8')

    def get_task_script(self) -> str:
        return self._get_bash_script()

    def _get_bash_script(self) -> str:
        """
        get the bash for the next task
        """

        script = (
            "#export PATH=$PATH\n"
            f"cd {self._config_path}\n"
            f"{self._python} {self._python_script} {self._config_path}/config.{self._next_task}.json >"
            f"{self._working_path}/python_script.{self._next_task}.log\n"
        )
        self._next_task += 1
        return script


class PythonAWSTaskFactory(PythonTaskFactory):

    def __init__(self, working_path: Path | PurePath | str, python_script_module: ModuleType, **kwargs):
        super().__init__(working_path, python_script_module, **kwargs)


class PythonPBSTaskFactory(PythonTaskFactory):

    def __init__(
        self,
        root_path: Path | PurePath | str,
        working_path: Path | PurePath | str,
        python_script_module: ModuleType,
        **kwargs,
    ):

        super().__init__(working_path, python_script_module, **kwargs)

        self._pbs_ppn = kwargs.get('pbs_ppn', 16)  # define hows many processors the PBS job should 'see'
        self._pbs_nodes = 1  # always ust one PBS node (and which one we don't know)
        self._pbs_wall_hours = kwargs.get('pbs_wall_hours', 1)  # defines maximum time the jobs is allocated by PBS

    def write_task_config(self, task_args: BaseModel, task_system_args: BaseModel):
        raise NotImplementedError("PythonPBSTaskFactory.write_task_config not implemented. Need to fix wall hours")
        # fname = self._config_path / f"config.{self._next_port}.json"
        # if isinstance(task_args, InversionArgs):
        #     max_inversion_time = task_args.task.max_inversion_time[0]
        #     self._pbs_wall_hours = int(max_inversion_time / 60) + 1
        #     self._pbs_ppn = task_args.general.java_threads

        # task_config = get_task_config(task_args, task_system_args)
        # fname.write_text(json.dumps(task_config, indent=4), encoding='utf-8')

    def get_task_script(self) -> str:
        return f"""
#PBS -l nodes={self._pbs_nodes}:ppn={self._pbs_ppn}
#PBS -l walltime={self._pbs_wall_hours}:00:00
#PBS -l mem={int(self._jvm_heap_max_gb)+2}gb

source {self._root_path}/nzshm-runzi/bin/activate

export http_proxy=http://beavan:8899/
export https_proxy=${{http_proxy}}
export HTTP_PROXY=${{http_proxy}}
export HTTPS_PROXY=${{http_proxy}}
export no_proxy="127.0.0.1,localhost"
export NO_PROXY=${{no_proxy}}

{self._get_bash_script()}

#END_OF_PBS
"""


def get_factory(environment_mode) -> type[PythonTaskFactory]:
    if environment_mode == EnvMode['LOCAL']:
        return PythonTaskFactory
    elif environment_mode == EnvMode['CLUSTER']:
        return PythonPBSTaskFactory
    elif environment_mode == EnvMode['AWS']:
        return PythonAWSTaskFactory
