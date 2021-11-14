import boto3
import json

def main(id):
    topicArn = 'arn:aws:sns:us-east-1:280294454685:runzi-inversion-diagnostics.fifo'
    session = boto3.session.Session(region_name='us-east-1', profile_name='runzi-report-bucket')
    sns = session.client('sns')
    publishObject = { "model_id": id, "bing": "bongbash" }
    response = sns.publish(
        TopicArn=topicArn,
        Message=json.dumps(publishObject),
        Subject='task',
        MessageAttributes= {'id': { "DataType": "String", "StringValue": "id"}},
        MessageDeduplicationId='Runzi123456',
        MessageGroupId="RUNZI")
    
    print(response['ResponseMetadata']['HTTPStatusCode']) 

main("SW52ZXJzaW9uU29sdXRpb246MjMwNi4wU2lHM1E=")


 