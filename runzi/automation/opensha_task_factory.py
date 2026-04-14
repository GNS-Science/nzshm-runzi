#!python3

"""
Wrapper script that produces an Opensha job that can be run either locally or
to a cluster using PBS

The job is responsible for

 - launching the java application (with its gateway service configured)
 - executing the python client script + config that calls the Java application
 - updating the task status, files etc via the toshi_api
 - shutting down the java app

 The job is either a bash script (for local machine) or
 a PBS script for the cluster environment
"""

import json
import os
from pathlib import Path, PurePath
from typing import Optional, Protocol, TypeVar

from pydantic import BaseModel

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.python_task_factory import PythonTaskFactory, get_factory as get_python_factory
from runzi.automation.task_config import get_task_config
from runzi.automation.toshi_api import ModelType
from runzi.protocols import ModuleWithDefaultSysArgs

from .local_config import ClusterModeEnum

# from runzi.runners.inversion_inputs import InversionArgs


OpenshaTaskFactoryType = TypeVar("OpenshaTaskFactoryType", bound="OpenshaTaskFactory")

# import scaling.rupture_set_builder_task


class TaskFactory(Protocol):
    def write_task_config(self, task_args: BaseModel, task_system_args: SystemArgs, model_type: ModelType) -> None: ...

    def get_container_task(self) -> str: ...

    def get_task_script(self) -> str: ...

    def get_next_port(self) -> int: ...

    @classmethod
    def create(cls, **kwargs) -> "TaskFactory": ...


class OpenshaTaskFactory:
    def __init__(
        self,
        root_path: Path | PurePath | str,
        working_path: Path | PurePath | str,
        python_script_module: ModuleWithDefaultSysArgs,
        jre_path: Path | PurePath | str,
        app_jar_path: Path | PurePath | str,
        task_config_path: Optional[Path | PurePath | str] = None,
        initial_gateway_port: int = 25333,
        python: str = "python3",
        jvm_heap_start: int = 3,
        jvm_heap_max: int = 10,
    ):
        """
        initial_gateway_port: what port to start incrementing from
        """
        self._next_port = initial_gateway_port

        self._jre_path = jre_path
        self._app_jar_path = app_jar_path
        self._config_path = Path(task_config_path or Path.cwd())
        # self._script_path = os.path.dirname(scaling.rupture_set_builder_task.__file__) #path to the actual task script
        self._python_script = os.path.abspath(python_script_module.__file__)  # type: ignore

        self._root_path = root_path  # path containing the git repos
        self._working_path = working_path

        self._jvm_heap_start_gb = str(jvm_heap_start)
        self._jvm_heap_max_gb = str(jvm_heap_max)
        self._python = str(python)
        # self._python_script = python_script or 'rupture_set_builder_task.py'

    @classmethod
    def create(cls, **kwargs) -> "TaskFactory":
        return cls(
            kwargs["root_path"],
            kwargs["working_path"],
            kwargs["python_script_module"],
            jre_path=kwargs["jre_path"],
            app_jar_path=kwargs["app_jar_path"],
            task_config_path=kwargs.get("task_config_path"),
            initial_gateway_port=kwargs.get("initial_gateway_port", 25333),
            python=kwargs.get("python", "python3"),
            jvm_heap_start=kwargs.get("jvm_heap_start", 3),
            jvm_heap_max=kwargs.get("jvm_heap_max", 10),
        )

    def get_container_task(self) -> str:
        return ""

    def write_task_config(self, task_args: BaseModel, task_system_args: SystemArgs, model_type: ModelType):
        fname = self._config_path / f"config.{self._next_port}.json"
        task_config = get_task_config(task_args, task_system_args, model_type)
        fname.write_text(json.dumps(task_config, indent=4), encoding="utf-8")

    def get_task_script(self) -> str:
        return self._get_bash_script()

    def get_next_port(self) -> int:
        return self._next_port

    def _get_bash_script(self) -> str:
        """
        get the bash for the next task
        """

        script = (
            f"export PATH={self._jre_path}:$PATH\n"
            f"export JAVA_CLASSPATH={self._app_jar_path}\n"
            "export CLASSNAME=nz.cri.gns.NZSHM22.opensha.util.NZSHM22_PythonGateway\n"
            f"export NZSHM22_APP_PORT={self._next_port}\n"
            f"cd {self._root_path}\n"
            f"java -Xms{self._jvm_heap_start_gb}G -Xmx{self._jvm_heap_max_gb}G"
            f" -classpath ${{JAVA_CLASSPATH}} ${{CLASSNAME}} > "
            f"{self._working_path}/java_app.{self._next_port}.log &\n"
            f"{self._python} {self._python_script} {self._config_path}/config.{self._next_port}.json > "
            f"{self._working_path}/python_script.{self._next_port}.log\n"
            # Kill the Java gateway server
            "kill -9 $!"
        )
        self._next_port += 1
        return script


class OpenshaAWSTaskFactory(OpenshaTaskFactory):
    def __init__(self, root_path, working_path, python_script_module, **kwargs):
        super().__init__(root_path, working_path, python_script_module, **kwargs)

    def get_container_task(self) -> str:
        return "java_container_task.sh"


#     def get_task_script(self):

#         fname = f"{self._config_path}/config.{self._next_port}.json"

#         return f"""
# #AWS GENERAL RUN SCRIPT....

# # expects an env TASK_CONFIG_JSON_QUOTED built like urllib.parse.quote(config_dict)
# export TASK_CONFIG_JSON_QUOTED=
# export PYTHON_TASK_MODULE={self._python_script}

# #DO the AWS stuff here to execute this againts the cloud container

# ./container_task.sh

# #END
# """


class OpenshaPBSTaskFactory(OpenshaTaskFactory):
    def __init__(
        self,
        root_path: Path | PurePath | str,
        working_path: Path | PurePath | str,
        python_script_module: ModuleWithDefaultSysArgs,
        **kwargs,
    ):

        super().__init__(root_path, working_path, python_script_module, **kwargs)

        self._pbs_ppn = kwargs.get("pbs_ppn", 16)  # define hows many processors the PBS job should 'see'
        self._pbs_nodes = 1  # always ust one PBS node (and which one we don't know)
        self._pbs_wall_hours = kwargs.get('pbs_wall_hours', 1)  # defines maximum time the jobs is allocated by PBS

    def get_container_task(self) -> str:
        return ""

    def write_task_config(self, task_args: BaseModel, task_system_args: SystemArgs, model_type: ModelType):
        fname = self._config_path / f"config.{self._next_port}.json"
        self._pbs_wall_hours = int(task_system_args.ecs_max_job_time_min / 60) + 1
        self._pbs_ppn = task_system_args.java_threads

        task_config = get_task_config(task_args, task_system_args, model_type)
        fname.write_text(json.dumps(task_config, indent=4), encoding="utf-8")

    def get_task_script(self) -> str:
        return f"""
#PBS -l nodes={self._pbs_nodes}:ppn={self._pbs_ppn}
#PBS -l walltime={self._pbs_wall_hours}:00:00
#PBS -l mem={int(self._jvm_heap_max_gb) + 2}gb

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


def get_java_factory(environment_mode: ClusterModeEnum) -> type[OpenshaTaskFactory]:
    match environment_mode:
        case ClusterModeEnum.LOCAL:
            return OpenshaTaskFactory
        case ClusterModeEnum.CLUSTER:
            return OpenshaPBSTaskFactory
        case ClusterModeEnum.AWS:
            return OpenshaAWSTaskFactory
        case _:
            raise ValueError(f"Unknown environment_mode: {environment_mode}")


def get_factory(
    environment_mode: ClusterModeEnum, task_language: TaskLanguage
) -> type[OpenshaTaskFactory | PythonTaskFactory]:
    match task_language:
        case TaskLanguage.JAVA:
            return get_java_factory(environment_mode)
        case TaskLanguage.PYTHON:
            return get_python_factory(environment_mode)
        case _:
            raise ValueError(f"Unknown task_language: {task_language}")
