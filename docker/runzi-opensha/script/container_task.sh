#This is the AWS CONTAINER SCRIPT

#export PATH=OPENSHA_JRE :$PATH

export JAVA_CLASSPATH=${NZSHM22_FATJAR}
export CLASSNAME=nz.cri.gns.NZSHM22.opensha.util.NZSHM22_PythonGateway
export NZSHM22_APP_PORT=26533

cd /app/nzshm-runzi

java -Xms4G -Xmx${NZSHM22_SCRIPT_JVM_HEAP_MAX}G -classpath ${JAVA_CLASSPATH} ${CLASSNAME} > ${NZSHM22_SCRIPT_WORK_PATH}/java_app.log &

python3 runzi/automation/scaling/inversion_solution_builder_task.py ${RUNZI_CONFIG_AS_JSON} > ${NZSHM22_SCRIPT_WORK_PATH}/python_script.log

#Kill the Java gateway server
kill -9 $!

#END_OF_SCRIPT