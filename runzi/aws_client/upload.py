import boto3
import os
from multiprocessing.pool import ThreadPool
import datetime as dt
import shutil

from runzi.automation.scaling.local_config import WORK_PATH, AGENT_S3_WORKERS
from env import AWS_ACCESS_KEY, AWS_SECRET_KEY

def upload_to_bucket(id, bucket):
    t0 = dt.datetime.utcnow()
    local_directory = WORK_PATH + '/' + id
    client = boto3.client('s3',
            region_name='us-east-1',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY)

    file_list = []
    for root, dirs, files in os.walk(local_directory):
        for filename in files:

            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_directory)
            s3_path = os.path.join(id, relative_path)

            file_list.append((local_path, bucket, s3_path))

    def unpack_and_upload(args):
        upload(args[0], args[1], args[2])

    def upload(local_path, bucket, s3_path):
        try:
            client.head_object(Bucket=bucket, Key=s3_path)
            print("Path found on S3! Skipping %s to %s" % (s3_path, bucket))

        except:
            print("Uploading %s..." % s3_path)
            client.upload_file(local_path, bucket, s3_path)
        
    pool = ThreadPool(processes=AGENT_S3_WORKERS)
    pool.map(unpack_and_upload, file_list)

    pool.close()
    pool.join()
    print("Done! uploaded %s in %s secs" % (len(file_list), (dt.datetime.utcnow() - t0).total_seconds()))
    cleanup(local_directory)

def cleanup(directory):
    shutil.rmtree(directory)
    print('Cleaned up %s' % directory)

upload_to_bucket("SW52ZXJzaW9uU29sdXRpb246MjMwNi4wU2lHM1E=", "nzshm-static-reports-test")