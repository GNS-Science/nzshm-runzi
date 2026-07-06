#This is the AWS CONTAINER SCRIPT for Java applications

export JAVA_CLASSPATH=${NZSHM22_FATJAR}
export CLASSNAME=nz.cri.gns.NZSHM22.opensha.util.NZSHM22_PythonGateway

# AWS Batch forces host networking on EC2, so every job container on an instance shares
# 127.0.0.1. A fixed gateway port makes concurrent jobs collide: the first JVM wins the port,
# the rest fail to bind, and their Python clients connect to the winner's JVM instead —
# corrupting results and writing solutions to the wrong container's filesystem. Pick a free
# ephemeral port per container at runtime; get_config() forwards NZSHM22_APP_PORT to the Python
# client so both ends of the py4j gateway agree on the same port.
export NZSHM22_APP_PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')

/opt/java/bin/java -Xms4G -Xmx${NZSHM22_SCRIPT_JVM_HEAP_MAX}G -XX:ActiveProcessorCount=${NZSHM22_AWS_JAVA_THREADS} -classpath ${JAVA_CLASSPATH} ${CLASSNAME} > ${NZSHM22_SCRIPT_WORK_PATH}/java_app.${NZSHM22_APP_PORT}.log &

# TODO: we can do away with PYTHON_PREP_MODULE
python3 -m ${PYTHON_TASK_MODULE} ${TASK_CONFIG_JSON_QUOTED} > ${NZSHM22_SCRIPT_WORK_PATH}/python_script.${NZSHM22_APP_PORT}.log

#Kill the Java gateway server
kill -9 $!

#END_OF_SCRIPT
