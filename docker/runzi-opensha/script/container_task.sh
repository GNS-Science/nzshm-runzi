#This is the AWS CONTAINER SCRIPT

#export PATH=OPENSHA_JRE :$PATH

export JAVA_CLASSPATH=${NZSHM22_FATJAR}
export CLASSNAME=nz.cri.gns.NZSHM22.opensha.util.NZSHM22_PythonGateway
export NZSHM22_APP_PORT=26533

cd /app/nzshm-runzi

java -Xms4G -Xmx${NZSHM22_SCRIPT_JVM_HEAP_MAX}G -XX:ActiveProcessorCount=${NZSHM22_AWS_JAVA_THREADS} -classpath ${JAVA_CLASSPATH} ${CLASSNAME} > ${NZSHM22_SCRIPT_WORK_PATH}/java_app.${NZSHM22_APP_PORT}.log &

# TODO: we can do away with PYTHON_PREP_MODULE
python3 -m ${PYTHON_TASK_MODULE} ${TASK_CONFIG_JSON_QUOTED} > ${NZSHM22_SCRIPT_WORK_PATH}/python_script.${NZSHM22_APP_PORT}.log

#Kill the Java gateway server
kill -9 $!

#END_OF_SCRIPT
