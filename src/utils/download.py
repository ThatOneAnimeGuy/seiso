from flask import current_app

import requests
import functools
import uuid
import hashlib
import time
import os
import shutil

from .proxy import get_proxy
from .utils import get_filename_from_cd, slugify, get_value, take, get_file_metadata, get_config, limit_string, sha256_file

def fetch_file_and_data(url, **kwargs):
    file_data = fetch_file_data(url, **kwargs)
    if file_data is None:
        return None

    (mime_type, extension) = get_file_metadata(file_data['local_path'])

    filename = get_value(file_data['headers'], 'x-amz-meta-original-filename')
    if filename is None:
        filename = get_filename_from_cd(get_value(file_data['headers'], 'content-disposition')) or (take(32, file_data['sha256']) + extension)
    filename = limit_string(slugify(filename), 255)

    return {
        'local_path': file_data['local_path'],
        'name': filename,
        'mime_type': mime_type,
        'extension': extension,
        'sha256': file_data['sha256'],
        'size': file_data['size'],
    }

def fetch_file_data(url, **kwargs):
    attempts = kwargs.pop('attempts', 10)
    resource_id = kwargs.pop('resource_id', '')
    try:
        r = requests.get(url, stream = True, proxies = get_proxy(), **kwargs)
        if r.status_code in [400, 401, 403, 404]:
            return None

        r.raise_for_status()
        r.raw.read = functools.partial(r.raw.read, decode_content = True)

        if 'text/html' in get_value(r.headers, 'content-type'):
            return None

        file_size = None
        local_path = os.path.join(get_config('TEMP_STORAGE_DIR'), resource_id)
        local_file = os.path.join(local_path, str(uuid.uuid4()))
        create_dir_if_not_exists(local_path)
        with open(local_file, 'wb') as f:
            shutil.copyfileobj(r.raw, f)
            file_size = f.tell()

        content_length = get_value(r.headers, 'content-length')
        if content_length is not None and file_size != int(content_length):
            raise Exception(f'File size is not the same as the content-length header says it should be ({content_length} bytes vs actual {file_size} bytes)')

        sha256 = sha256_file(local_file)
        return {
            'headers': r.headers,
            'local_path': local_file,
            'sha256': sha256,
            'size': file_size,
        }
    except:
        if attempts > 1:
            current_app.logger.error(f'Error fetching url: {url}. Sleeping for 30s before trying again. {attempts - 1} attempts remaining.')
            time.sleep(30)
            return fetch_file_data(url, attempts = attempts - 1, resource_id = resource_id, **kwargs)
        else:
            current_app.logger.exception(f'Error fetching url: {url}. All attempts exhausted.')
            raise

def initialize_temp_download_directory():
    directory = get_config('TEMP_STORAGE_DIR')
    if os.path.isdir(directory):
        shutil.rmtree(directory)
    os.makedirs(directory, exist_ok = True)

def create_dir_if_not_exists(directory):
    os.makedirs(directory, exist_ok = True)

def remove_temp_files(resource_id):
    directory = os.path.join(get_config('TEMP_STORAGE_DIR'), resource_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory)
