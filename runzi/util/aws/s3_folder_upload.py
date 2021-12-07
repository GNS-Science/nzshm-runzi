from botocore.errorfactory import ClientError
import boto3
import boto3.session
from botocore.exceptions import ClientError
import os
from multiprocessing.pool import ThreadPool
import datetime as dt
import shutil
import mimetypes 
import logging
from logging import info, error
import backoff
import botocore.exceptions

from runzi.automation.scaling.local_config import WORK_PATH, S3_UPLOAD_WORKERS


logging.basicConfig(level="INFO")
S3_REPORT_BUCKET_ROOT = 'opensha/DATA'

def check_if_slowdown(e):
    try:
        return e.response['Error']['Code'] == 'SlowDown'
    except AttributeError:
        return False

def upload_to_bucket(id, bucket, root_path=S3_REPORT_BUCKET_ROOT):
    info(f"Beginning bucket upload... to {bucket}/{root_path}/{id}")
    t0 = dt.datetime.utcnow()
    local_directory = WORK_PATH + '/' + id
    session = boto3.session.Session()
    client = session.client('s3')
    file_list = []
    for root, dirs, files in os.walk(local_directory):
        for filename in files:

            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_directory)
            s3_path = os.path.join(root_path, id, relative_path)
            file_list.append((local_path, bucket, s3_path))
    
    @backoff.on_predicate(backoff.expo, check_if_slowdown)
    def upload(args):
        """Map function for pool, uploads to S3 Bucket if it doesn't exist already"""
        local_path, bucket, s3_path = args[0], args[1], args[2]

        if path_exists(s3_path, bucket):
            info("Path found on S3! Skipping %s to %s" % (s3_path, bucket))

        else:
            try:
                client.upload_file(local_path, bucket, s3_path,
                    ExtraArgs={
                        'ACL':'public-read',
                        'ContentType': mimetype(local_path)
                        })
                info("Uploading %s..." % s3_path)
            except ClientError as e:
                error(f"exception raised uploading {local_path} => {bucket}/{s3_path}")
                error(e)
    
    def path_exists(path, bucket_name):
        """Check to see if an object exists on S3"""
        try:
            response = client.list_objects_v2(Bucket=bucket_name, Prefix=path)
            if response:
                if response['KeyCount'] == 0:
                    return False
                else:    
                    for obj in response['Contents']:
                        if path == obj['Key']:
                            return True
        except ClientError as e:
                error(f"exception raised on {bucket_name}/{path}")
                raise e

        
    pool = ThreadPool(processes=S3_UPLOAD_WORKERS)
    pool.map(upload, file_list)

    pool.close()
    pool.join()
    info("Done! uploaded %s in %s secs" % (len(file_list), (dt.datetime.utcnow() - t0).total_seconds()))
    cleanup(local_directory)

def cleanup(directory):
    try:
        shutil.rmtree(directory)
        info('Cleaned up %s' % directory)
    except Exception as e:
        error(e)

def mimetype(local_path):
    mimetypes.add_type('text/markdown', '.md')
    mimetypes.add_type('application/json', '.geojson')
    mimetype, _ = mimetypes.guess_type(local_path)
    if mimetype is None:
        raise Exception("Failed to guess mimetype")
    return mimetype
