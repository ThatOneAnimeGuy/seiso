import boto3
import logging
import requests
import io
import os

from flask import current_app

from .utils import get_config

def get_client():
    session = boto3.session.Session()
    return session.client(
        service_name = 's3',
        region_name = get_config('S3_REGION_NAME'),
        use_ssl = get_config('S3_USE_SSL'),
        endpoint_url = get_config('S3_ENDPOINT_URL'),
        aws_access_key_id = get_config('S3_AWS_ACCESS_KEY_ID'),
        aws_secret_access_key = get_config('S3_AWS_SECRET_ACCESS_KEY')
    )

def upload_file_bytes(name, file_bytes, mime_type = 'binary/octet-stream', public = False):
    with io.BytesIO(file_bytes) as f:
        upload_file_object(name, f, mime_type, public)

def upload_file(name, file_path, mime_type = 'binary/octet-stream', public = False, delete_local_after_upload = True):
    with open(file_path, 'rb') as f:
        upload_file_object(name, f, mime_type, public)

    if delete_local_after_upload:
        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            current_app.logger.warning(f'Did not delete {file_path}')
    else:
        current_app.logger.warning(f'Did not delete {file_path} because delete_local_after_upload was False')

def upload_file_object(name, file_object, mime_type = 'binary/octet-stream', public = False):
    try:
        extra_args = {
            'ContentType': mime_type
        }
        if public:
            extra_args['ACL'] = 'public-read'

        client = get_client()
        client.upload_fileobj(file_object, get_config('S3_BUCKET_NAME'), name, ExtraArgs = extra_args)
    except:
        current_app.logger.exception(f'Error uploading file {name}')
        raise

def delete_file(name, bucket_name):
    try:
        client = get_client()
        client.delete_object(Bucket = bucket_name, Key = name)
    except:
        current_app.logger.exception(f'Error deleting file {name}')
        raise
