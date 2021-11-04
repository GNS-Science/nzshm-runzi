import boto3
import os

from runzi.automation.scaling.local_config import WORK_PATH
from env import AWS_ACCESS_KEY, AWS_SECRET_KEY

def upload_to_bucket(id, bucket):
    local_directory = WORK_PATH + '/' + id
    client = boto3.client('s3',
            region_name='us-east-1',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY)

    for root, dirs, files in os.walk(local_directory):
        for filename in files:

            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_directory)
            s3_path = os.path.join(id, relative_path)

            try:
                client.head_object(Bucket=bucket, Key=s3_path)
                print("Path found on S3! Skipping %s to %s" % (s3_path, bucket))

            except:
                print("Uploading %s..." % s3_path)
                client.upload_file(local_path, bucket, s3_path)
    