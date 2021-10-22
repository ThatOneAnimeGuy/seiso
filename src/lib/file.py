from flask import current_app

from ..internals.database.database import get_cursor
from ..utils.utils import is_mime_type_image, get_value, get_config
from ..utils.object_storage import upload_file, upload_file_bytes
from ..utils.image_processing import make_preview

def does_post_file_exist(file):
    query = "SELECT id FROM post_file WHERE sha256_hash = %s AND post_id = %s"
    with get_cursor() as cursor:
        cursor.execute(query, (file['sha256'], file['post_id'],))
        results = cursor.fetchall()
    if len(results) > 0:
        return True
    return False

def get_post_file(file_id):
    query = 'SELECT * FROM post_file WHERE id = %s'
    with get_cursor() as cursor:
        cursor.execute(query, (file_id,))
        return cursor.fetchone()

def get_post_file_id(post_id, file_hash):
    query = "SELECT id FROM post_file WHERE sha256_hash = %s AND post_id = %s"
    with get_cursor() as cursor:
        cursor.execute(query, (file_hash, post_id,))
        results = cursor.fetchall()
    if len(results) > 0:
        return results[0]['id']
    return None

def is_post_file_upload_finished(post_file_id):
    query = "SELECT is_upload_finished FROM post_file WHERE id = %s"
    with get_cursor() as cursor:
        cursor.execute(query, (post_file_id,))
        return cursor.fetchone()['is_upload_finished']

def insert_post_file(file):
    query = "INSERT INTO post_file (post_id, sha256_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id"
    with get_cursor() as cursor:
        cursor.execute(query, (file['post_id'], file['sha256']))
        result = cursor.fetchone()

    if result is None:
        file_id = get_post_file_id(file['post_id'], file['sha256'])
        saved_file = get_post_file(file_id)
        if get_value(file, 'sub_id') != get_value(saved_file, 'sub_id'):
            with get_cursor() as cursor:
                cursor.execute('UPDATE post_file SET sub_id = %s WHERE id = %s', (get_value(file, 'sub_id'), file_id,))
        return file_id
    return result['id']

def mark_post_file_upload_finished(post_file_id, file):
    with get_cursor() as cursor:
        query = "UPDATE post_file SET is_upload_finished = true, name = %s, path = %s, mime_type = %s, is_inline = %s, inline_content = %s, file_size = %s, bucket_name = %s, comment = %s, sub_id = %s WHERE id = %s"
        cursor.execute(query, (
            file['name'],
            file['path'],
            file['mime_type'],
            get_value(file, 'is_inline', False),
            get_value(file, 'inline_content'),
            get_value(file, 'size'),
            get_config('S3_BUCKET_NAME'),
            get_value(file, 'comment'),
            get_value(file, 'sub_id'),
            post_file_id,
        ))

def set_post_file_preview(post_file_id, preview_path):
    with get_cursor() as cursor:
        cursor.execute("UPDATE post_file SET preview_path = %s WHERE id = %s", (preview_path, post_file_id,))

def insert_and_upload_post_file(file):
    post_file_id = insert_post_file(file)
    if not is_post_file_upload_finished(post_file_id):
        make_and_upload_post_preview(file, post_file_id)
        upload_file(file['path'], file['local_path'], file['mime_type'])
        mark_post_file_upload_finished(post_file_id, file)
    return post_file_id

def make_and_upload_post_preview(file, post_file_id):
    post_id = file['post_id']
    if is_mime_type_image(file['mime_type']):
        preview_path = f'previews/{file["service"]}/{post_id}/{file["name"]}'
        image = make_preview(file['local_path'])
        if image is None:
            current_app.logger.debug(f'Skipping preview for file {post_file_id} (mime: {file["mime_type"]})')
            return

        (preview_bytes, preview_mime) = image
        upload_file_bytes(preview_path, preview_bytes, preview_mime)
        set_post_file_preview(post_file_id, preview_path)

def clean_up_unfinished_files(post_id):
    with get_cursor() as cursor:
        query = 'DELETE FROM post_file WHERE post_id = %s AND is_upload_finished = false'
        cursor.execute(query, (post_id,))
