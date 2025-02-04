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

from .local_config import EnvMode


class PythonTaskFactory:

    def __init__(self, working_path, python_script_module, task_config_path=None, python='python3'):

        self._config_path = task_config_path or os.getcwd()
        self._python_script = os.path.abspath(python_script_module.__file__)
        self._working_path = working_path
        self._python = str(python)
        self._next_task = 1

    def write_task_config(self, task_arguments, job_arguments):
        data = dict(task_arguments=task_arguments, job_arguments=job_arguments)
        fname = f"{self._config_path}/config.{self._next_task}.json"
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get_task_script(self):
        return self._get_bash_script(), self._next_task - 1

    def _get_bash_script(self):
        """
        get the bash for the next task
        """

        script = f"""
#export PATH=$PATH

{self._python} {self._python_script} {self._config_path}/config.{self._next_task}.json > {self._working_path}/python_script.{self._next_task}.log
"""
        self._next_task += 1
        return script


class PythonAWSTaskFactory(PythonTaskFactory):

    def __init__(self, working_path, python_script_module, **kwargs):
        super().__init__(working_path, python_script_module, **kwargs)


class PythonPBSTaskFactory(PythonTaskFactory):

    def __init__(self, root_path, working_path, python_script_module, **kwargs):

        super().__init__(working_path, python_script_module, **kwargs)

        self._pbs_ppn = kwargs.get('pbs_ppn', 16)  # define hows many processors the PBS job should 'see'
        self._pbs_nodes = 1  # always ust one PBS node (and which one we don't know)
        self._pbs_wall_hours = kwargs.get('pbs_wall_hours', 1)  # defines maximum time the jobs is allocated by PBS

    def write_task_config(self, task_arguments, job_arguments):
        data = dict(task_arguments=task_arguments, job_arguments=job_arguments)
        fname = f"{self._config_path}/config.{self._next_port}.json"
        if task_arguments.get('max_inversion_time'):
            self._pbs_wall_hours = int(float(task_arguments.get('max_inversion_time')) / 60) + 1
        if job_arguments.get('threads'):
            self._pbs_ppn = int(job_arguments.get('threads'))

        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get_task_script(self):
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


def get_factory(environment_mode):
    if environment_mode == EnvMode['LOCAL']:
        return PythonTaskFactory
    elif environment_mode == EnvMode['CLUSTER']:
        return PythonPBSTaskFactory
    elif environment_mode == EnvMode['AWS']:
        return PythonAWSTaskFactory
