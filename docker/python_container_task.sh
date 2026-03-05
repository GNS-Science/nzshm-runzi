#This is the AWS CONTAINER SCRIPT for Python applications

cd /app/nzshm-runzi

python3 -m ${PYTHON_TASK_MODULE} ${TASK_CONFIG_JSON_QUOTED}
#END_OF_SCRIPT
