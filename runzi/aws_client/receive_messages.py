from os import read
import boto3
import json
import time
import schedule
from env import AWS_ACCESS_KEY, AWS_SECRET_KEY
from inversion_diagnostic_runner import run_inversion_diags


def read_message_and_run_diagnostics():
    sqs = boto3.client('sqs', 
                        region_name='us-east-1',
                        aws_access_key_id=AWS_ACCESS_KEY,
                        aws_secret_access_key=AWS_SECRET_KEY)
    queueUrl="https://sqs.us-east-1.amazonaws.com/280294454685/runzi-inversion-diagnostics-queue.fifo"

    try:
        response = sqs.receive_message(
        QueueUrl=queueUrl,
        AttributeNames=[
            'All'
        ],
        MaxNumberOfMessages=1,
        VisibilityTimeout=100,
        WaitTimeSeconds=0)
    except Exception as e:
        print(e)

    try:
        message = response['Messages'][0]
        receipt_handle = message['ReceiptHandle']

        sqs.delete_message(
            QueueUrl=queueUrl,
            ReceiptHandle=receipt_handle
        )
        task_id = json.loads(json.loads(message['Body'])['Message'])['model_id']
        print('Received and deleted message with id: %s' % task_id)
        print("Running diagnostics...")
        run_inversion_diags(task_id)
    except KeyError:
        print('No tasks to run - back to sleep!')

schedule.every(1).minutes.do(read_message_and_run_diagnostics)
while True:
    schedule.run_pending()
    time.sleep(1)

