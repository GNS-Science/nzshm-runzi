from botocore.errorfactory import ClientError
import boto3
import boto3.session
import os
from multiprocessing.pool import ThreadPool
import datetime as dt
import shutil
from botocore.retries.standard import ExponentialBackoff

from runzi.automation.scaling.local_config import WORK_PATH, AGENT_S3_WORKERS, S3_PROFILE

def upload_to_bucket(id, bucket):
    t0 = dt.datetime.utcnow()
    local_directory = WORK_PATH + '/' + id
    session = boto3.session.Session(region_name='us-east-1', profile_name='runzi-report-bucket')
    client = session.client('s3')

    file_list = []
    for root, dirs, files in os.walk(local_directory):
        for filename in files:

            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_directory)
            s3_path = os.path.join(id, relative_path)

            file_list.append((local_path, bucket, s3_path))

    def upload(args):
        local_path, bucket, s3_path = args[0], args[1], args[2]

        if path_exists(s3_path, bucket):
            print("Path found on S3! Skipping %s to %s" % (s3_path, bucket))

        else:
            try:
                client.upload_file(local_path, bucket, s3_path)
                print("Uploading %s..." % s3_path)

            except Exception as e:
                print(e)
    
    def path_exists(path, bucket_name):
        """Check to see if an object exists on S3"""
        s3 = boto3.resource('s3')
        try:
            s3.ObjectSummary(bucket_name=bucket_name, key=path).load()
        except ClientError as e:
            if e.response['Error']['Code'] == "404":
                return False
            else:
                raise e
        return True
        
    pool = ThreadPool(processes=AGENT_S3_WORKERS)
    pool.map(upload, file_list)

    pool.close()
    pool.join()
    print("Done! uploaded %s in %s secs" % (len(file_list), (dt.datetime.utcnow() - t0).total_seconds()))
    cleanup(local_directory)

def cleanup(directory):
    try:
        shutil.rmtree(directory)
        print('Cleaned up %s' % directory)
    except Exception as e:
        print(e)
