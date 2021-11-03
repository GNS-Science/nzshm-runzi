#!python3

"""
Wrapper script that produces a job that can be run either locally or
to a cluster using PBS

The job is responsible for

 - launching the java application (with its gateway service configured)
 - executing the python client script + config that calls the Java application
 - updating the task status, files etc via the toshi_api
 - shutting down the java app

 The job is either a bash script (for local machine) or
 a PBS script for the cluster environment
"""
import os
import json
# import scaling.rupture_set_builder_task

from .local_config import EnvMode


class OpenshaTaskFactory():

    def __init__(self, root_path, working_path,  python_script_module, jre_path=None, app_jar_path=None, task_config_path=None,
        initial_gateway_port=25333,
        python='python3',
        jvm_heap_start=3, jvm_heap_max=10):
        """
        initial_gateway_port: what port to start incrementing from
        """
        self._next_port = initial_gateway_port


        self._jre_path = jre_path or "/opt/sw/java/java-11-openjdk-amd64/bin/java"
        self._app_jar_path = app_jar_path or "~/NSHM/opensha/nshm-nz-opensha/build/libs/nshm-nz-opensha-all.jar"
        self._config_path = task_config_path or os.getcwd()
        # self._script_path = os.path.dirname(scaling.rupture_set_builder_task.__file__) #path to the actual task script
        self._python_script = os.path.abspath(python_script_module.__file__)

        self._root_path = root_path #path containing the git repos
        self._working_path = working_path

        self._jvm_heap_start_gb = str(jvm_heap_start)
        self._jvm_heap_max_gb = str(jvm_heap_max)
        self._python = str(python)
        # self._python_script = python_script or 'rupture_set_builder_task.py'

    def write_task_config(self, task_arguments, job_arguments):
        data =dict(task_arguments=task_arguments, job_arguments=job_arguments)
        fname = f"{self._config_path}/config.{self._next_port}.json"
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


    def get_task_script(self):
        return self._get_bash_script()

    def get_next_port(self):
        return self._next_port

    def _get_bash_script(self):
        """
        get the bash for the next task
        """

        script = f"""
export PATH={self._jre_path}:$PATH
export JAVA_CLASSPATH={self._app_jar_path}
export CLASSNAME=nz.cri.gns.NZSHM22.opensha.util.NZSHM22_PythonGateway
export NZSHM22_APP_PORT={self._next_port}

cd {self._root_path}
java -Xms{self._jvm_heap_start_gb}G -Xmx{self._jvm_heap_max_gb}G -classpath ${{JAVA_CLASSPATH}} ${{CLASSNAME}} > {self._working_path}/java_app.{self._next_port}.log &
{self._python} {self._python_script} {self._config_path}/config.{self._next_port}.json > {self._working_path}/python_script.{self._next_port}.log

#Kill the Java gateway server
kill -9 $!
"""
        self._next_port +=1
        return script

class OpenshaAWSTaskFactory(OpenshaTaskFactory):

    def __init__(self, root_path, working_path,  python_script_module, **kwargs):

        super().__init__(root_path, working_path,  python_script_module, **kwargs)

    def get_task_script(self):

        fname = f"{self._config_path}/config.{self._next_port}.json"

        return f"""
#AWS GENERAL RUN SCRIPT....

# expects an env TASK_CONFIG_JSON_QUOTED built like urllib.parse.quote(config_dict)
export TASK_CONFIG_JSON_QUOTED=
export PYTHON_TASK_MODULE={self._python_script}

#DO the AWS stuff here to execute this againts the cloud container

./container_task.sh

#END
"""


class OpenshaPBSTaskFactory(OpenshaTaskFactory):

    def __init__(self, root_path, working_path,  python_script_module, **kwargs):

        super().__init__(root_path, working_path,  python_script_module, **kwargs)

        self._pbs_ppn = kwargs.get('pbs_ppn', 16) #define hows many processors the PBS job should 'see'
        self._pbs_nodes = 1 #always ust one PBS node (and which one we don't know)
        self._pbs_wall_hours = kwargs.get('pbs_wall_hours', 1) #defines maximum time the jobs is allocated by PBS


    def write_task_config(self, task_arguments, job_arguments):
        data =dict(task_arguments=task_arguments, job_arguments=job_arguments)
        fname = f"{self._config_path}/config.{self._next_port}.json"
        if task_arguments.get('max_inversion_time'):
            self._pbs_wall_hours = int(float(task_arguments.get('max_inversion_time'))/60) + 1
        if job_arguments.get('java_threads'):
            self._pbs_ppn = int(job_arguments.get('java_threads'))

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
        return OpenshaTaskFactory
    elif environment_mode == EnvMode['CLUSTER']:
        return OpenshaPBSTaskFactory
    elif environment_mode == EnvMode['AWS']:
        return OpenshaAWSTaskFactory
