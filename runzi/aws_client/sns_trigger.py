import boto3
import json
from env import AWS_ACCESS_KEY, AWS_SECRET_KEY

def main(id):
    topicArn = 'arn:aws:sns:us-east-1:280294454685:runzi-inversion-diagnostics.fifo'
    snsClient = boto3.client(
        'sns',
        aws_access_key_id = AWS_ACCESS_KEY,
        aws_secret_access_key = AWS_SECRET_KEY,
        region_name = 'us-east-1'
    )
    publishObject = { "model_id": id, "bing": "bongbash" }
    response = snsClient.publish(
        TopicArn=topicArn,
        Message=json.dumps(publishObject),
        Subject='task',
        MessageAttributes= {'id': { "DataType": "String", "StringValue": "id"}},
        MessageDeduplicationId='Runzi123456',
        MessageGroupId="RUNZI")
    
    print(response['ResponseMetadata']['HTTPStatusCode']) 

main("SW52ZXJzaW9uU29sdXRpb246MjMwNi4wU2lHM1E=")


 