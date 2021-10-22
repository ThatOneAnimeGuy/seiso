from flask import current_app

import datetime
import re

from ..internals.cache.redis import get_redis, serialize, deserialize, delete_keys
from ..internals.database.database import get_cursor, get_conn
from ..utils.utils import get_value, is_mime_type_image, take, offset, get_config
from ..utils.object_storage import upload_file_bytes, delete_file
from ..utils.image_processing import make_thumbnail
from .file import clean_up_unfinished_files
from .artist import get_artist_post_count, get_artist, set_artist_last_post_imported_at_now

def get_random_posts_keys(count, reload = False):
    redis = get_redis()
    key = f'random_post_keys:{count}'
    post_keys = redis.get(key)
    if post_keys is None or reload:
        with get_cursor() as cursor:
            query = "SELECT p.id id FROM post p INNER JOIN post_file pf ON p.id = pf.post_id WHERE p.is_import_finished = true ORDER BY random() LIMIT %s"
            cursor.execute(query, (count,))
            post_keys = [row['id'] for row in cursor.fetchall()]
        redis.set(key, serialize(post_keys), ex = 900)
    else:
        post_keys = deserialize(post_keys)
    return post_keys

def get_post(post_id, minimal = False, reload = False):
    redis = get_redis()
    key = f'post_v3:{post_id}:{minimal}'
    post = redis.get(key)
    if post is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT p.*, a.service as service FROM post p INNER JOIN artist a ON a.id = p.artist_id WHERE p.id = %s AND is_import_finished = true'
            cursor.execute(query, (post_id,))
            post = cursor.fetchone()

        if post is not None and not minimal:
            post['files'] = get_post_files(post_id, reload)
            post['embeds'] = get_post_embeds(post_id, reload)
            post['extra_contents'] = get_post_extra_contents(post_id, reload)

        redis.set(key, serialize(post))
    else:
        post = deserialize(post)
    return post

def get_post_extra_contents(post_id, reload = False):
    redis = get_redis()
    key = f'post_extra_contents:{post_id}'
    contents = redis.get(key)
    if contents is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT title, content FROM extra_post_content WHERE post_id = %s ORDER BY id ASC'
            cursor.execute(query, (post_id,))
            contents = cursor.fetchall()
        redis.set(key, serialize(contents))
    else:
        contents = deserialize(contents)
    return contents

def get_post_files(post_id, reload = False):
    redis = get_redis()
    key = f'post_files_v2:{post_id}'
    files = redis.get(key)
    if files is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT * FROM post_file WHERE post_id = %s AND is_upload_finished = true ORDER BY id ASC'
            cursor.execute(query, (post_id,))
            files = cursor.fetchall()
        redis.set(key, serialize(files))
    else:
        files = deserialize(files)
    return files

def get_post_embeds(post_id, reload = False):
    redis = get_redis()
    key = f'post_embeds:{post_id}'
    embeds = redis.get(key)
    if embeds is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT * FROM post_embed WHERE post_id = %s ORDER BY id ASC'
            cursor.execute(query, (post_id,))
            embeds = cursor.fetchall()
        redis.set(key, serialize(embeds))
    else:
        embeds = deserialize(embeds)
    return embeds

def get_artist_posts_for_listing(artist_id, offset, reload = False):
    redis = get_redis()
    key = f'artist_posts_for_list_v2:{artist_id}:{offset}'
    posts = redis.get(key)
    if posts is None or reload:
        with get_cursor() as cursor:
            query = """
                SELECT p.*, count(pf.id) as file_count, a.service as service
                FROM post p
                INNER JOIN artist a ON p.artist_id = a.id
                LEFT JOIN post_file pf ON p.id = pf.post_id
                WHERE p.artist_id = %s AND p.is_import_finished = true
                GROUP BY p.id, a.service
                ORDER BY p.published_at DESC
                OFFSET %s
                LIMIT 25
            """
            cursor.execute(query, (artist_id, offset,))
            posts = cursor.fetchall()
        redis.set(key, serialize(posts))
    else:
        posts = deserialize(posts)
    return posts

def get_post_for_listing(post_id, reload = False):
    redis = get_redis()
    key = f'post_for_listing_v2:{post_id}'
    post = redis.get(key)
    if post is None or reload:
        with get_cursor() as cursor:
            query = """
                SELECT p.*, count(pf.id) as file_count, a.service as service
                FROM post p
                INNER JOIN artist a ON p.artist_id = a.id
                LEFT JOIN post_file pf ON p.id = pf.post_id
                WHERE p.id = %s AND p.is_import_finished = true
                GROUP BY p.id, a.service
            """
            cursor.execute(query, (post_id,))
            post = cursor.fetchone()
        redis.set(key, serialize(post))
    else:
        post = deserialize(post)
    return post

def get_artist_post_search_results(q, artist_id, o):
    with get_cursor() as cursor:
        query = """
            SELECT p.id post_id, count(pf.id) as file_count
            FROM post p
            INNER JOIN artist a ON p.artist_id = a.id
            LEFT JOIN post_file pf ON p.id = pf.post_id
            WHERE
                a.id = %s
                AND
                to_tsvector('english', p.content || ' ' || p.title) @@ websearch_to_tsquery(%s)
            GROUP BY p.id
            ORDER BY p.published_at DESC
        """
        cursor.execute(query, (artist_id, q))
        rows = cursor.fetchall()

    posts = []
    for row in take(25, offset(o, rows)):
        post = get_post(row['post_id'])
        post['file_count'] = row['file_count']
        posts.append(post)
    return (posts, len(rows))

def get_next_post_id(post_id, artist_id):
    with get_cursor() as cursor:
        query = """
            SELECT id
            FROM post
            WHERE
                post.artist_id = %s
                AND published_at < (
                    SELECT published_at
                    FROM post
                    WHERE
                        id = %s
                    LIMIT 1
                )
                AND is_import_finished = true
            ORDER BY published_at DESC
            LIMIT 1
        """
        cursor.execute(query, (artist_id, post_id,))
        next_post = cursor.fetchone()
        if next_post is not None:
            return next_post['id']
        return None

def get_previous_post_id(post_id, artist_id):
    with get_cursor() as cursor:
        query = """
            SELECT id
            FROM post
            WHERE
                post.artist_id = %s
                AND published_at > (
                    SELECT published_at
                    FROM post
                    WHERE
                        id = %s
                    LIMIT 1
                )
                AND is_import_finished = true
            ORDER BY published_at ASC
            LIMIT 1
        """
        cursor.execute(query, (artist_id, post_id,))
        prev_post = cursor.fetchone()
        if prev_post is not None:
            return prev_post['id']
        return None

def get_recent_posts_for_listing(offset):
    with get_cursor() as cursor:
        query = """
            SELECT
                p.*,
                (SELECT count(*) FROM post_file pf WHERE pf.post_id = p.id) as file_count,
                (SELECT service FROM artist a WHERE a.id = p.artist_id) as service
            FROM (
                SELECT *
                FROM post
                WHERE is_import_finished = true
                ORDER BY added_at DESC
                OFFSET %s
                LIMIT 25
            ) p
        """
        cursor.execute(query, (offset,))
        return cursor.fetchall()

def get_total_post_count(reload = False):
    redis = get_redis()
    key = f'total_post_count'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT count(*) as count FROM post WHERE is_import_finished = true'
            cursor.execute(query)
            count = cursor.fetchone()['count']
        redis.set(key, serialize(count), ex = 3600)
    else:
        count = deserialize(count)
    return count

def is_post_flagged(post_id, reload = False):
    redis = get_redis()
    key = f'post_flagged:{post_id}'
    flagged = redis.get(key)
    if flagged is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT 1 FROM reimport_flag WHERE post_id = %s'
            cursor.execute(query, (post_id,))
            flagged = cursor.fetchone() is not None
        redis.set(key, serialize(flagged))
    else:
        flagged = deserialize(flagged)
    return flagged

def mark_post_for_reimport(post_id):
    with get_cursor() as cursor:
        query = 'INSERT INTO reimport_flag (post_id) VALUES (%s) ON CONFLICT DO NOTHING'
        cursor.execute(query, (post_id,))
    is_post_flagged(post_id, True)

def insert_post(post):
    result = None
    with get_cursor() as cursor:
        query = "INSERT INTO post (service_id, artist_id, title, content, is_manual_upload, published_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id"
        cursor.execute(query, (post['service_id'], post['artist_id'], post['title'], post['content'], post['is_manual_upload'],
            post['published_at'], post['updated_at'],))
        result = cursor.fetchone()

    if result is None:
        return get_post_id_from_service_data(post['service'], post['service_artist_id'], post['service_id'])
    return result['id']

def update_post(post, post_id):
    with get_cursor() as cursor:
        query = "UPDATE post SET title = %s, content = %s, added_at = %s WHERE id = %s"
        cursor.execute(query, (post['title'], post['content'], post['added_at'], post_id,))

def set_post_import_not_finished(post_id, artist_id):
    with get_cursor() as cursor:
        cursor.execute("UPDATE post SET is_import_finished = false WHERE id = %s", (post_id,))

    get_post(post_id, True, True)
    get_post(post_id, False, True)
    get_post_for_listing(post_id, True)
    delete_keys(f'artist_posts_for_list:{artist_id}:*')

def finalize_post_import(post_id, artist_id):
    with get_cursor() as cursor:
        cursor.execute("UPDATE post SET is_import_finished = true WHERE id = %s", (post_id,))
        cursor.execute('DELETE FROM reimport_flag WHERE post_id = %s', (post_id,))

    set_artist_last_post_imported_at_now(artist_id)
    clean_up_unfinished_files(post_id)
    get_artist_post_count(artist_id, True)
    get_post(post_id, True, True)
    get_post(post_id, False, True)
    get_post_for_listing(post_id, True)
    delete_keys(f'artist_posts_for_list:{artist_id}:*')
    get_total_post_count(True)
    is_post_flagged(post_id, True)

def is_post_import_finished(service, service_artist_id, service_post_id):
     with get_cursor() as cursor:
        cursor.execute("SELECT p.id FROM post p INNER JOIN artist a ON p.artist_id = a.id WHERE p.service_id = %s AND a.service = %s AND a.service_id = %s AND p.is_import_finished = true", (service_post_id, service, service_artist_id,))
        return cursor.fetchone() is not None

def get_post_id_from_service_data(service, service_artist_id, service_post_id):
    with get_cursor() as cursor:
        cursor.execute("SELECT p.id as post_id FROM post p INNER JOIN artist a ON p.artist_id = a.id WHERE p.service_id = %s AND a.service = %s AND a.service_id = %s", (service_post_id, service, service_artist_id,))
        data = cursor.fetchall()

    if len(data) > 0:
        return data[0]['post_id']
    return None

def remove_post_if_flagged_for_reimport(service, service_artist_id, service_post_id):
    post_id = get_post_id_from_service_data(service, service_artist_id, service_post_id)
    if post_id is None:
        return False

    with get_cursor() as cursor:
        cursor.execute('SELECT 1 FROM reimport_flag WHERE post_id = %s', (post_id,))
        flag_exists = cursor.fetchone() is not None

    if not flag_exists:
        return False

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM post_file WHERE post_id = %s', (post_id,))
        cursor.execute('DELETE FROM post_embed WHERE post_id = %s', (post_id,))
        cursor.execute('DELETE FROM reimport_flag WHERE post_id = %s', (post_id,))
        cursor.execute('DELETE FROM extra_post_content WHERE post_id = %s', (post_id,))
        cursor.execute('UPDATE post SET is_import_finished = false, thumbnail_path = NULL, bucket_name = NULL WHERE id = %s', (post_id,))
        conn.commit()
        cursor.close()

    remove_post_files(post_id)

    return True

def post_is_missing_thumbnail(post_id):
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM post WHERE id = %s AND thumbnail_path IS NULL", (post_id,))
        return cursor.fetchone() is not None

def set_post_thumbnail(post_id, thumbnail_path):
    with get_cursor() as cursor:
        cursor.execute("UPDATE post SET thumbnail_path = %s, bucket_name = %s WHERE id = %s", (thumbnail_path, get_config('S3_BUCKET_NAME'), post_id,))

def get_post_embed_by_content(post_id, subject, description, url):
    with get_cursor() as cursor:
        query = 'SELECT * FROM post_embed WHERE post_id = %s AND subject = %s AND description = %s AND url = %s'
        cursor.execute(query, (post_id, subject, description, url,))
        return cursor.fetchone()

def insert_post_embed(post_id, embed):
    existing_embed = get_post_embed_by_content(post_id, embed['subject'], embed['description'], embed['url'])
    if existing_embed is not None and get_value(existing_embed, 'sub_id') != get_value(embed, 'sub_id'):
        with get_cursor() as cursor:
            cursor.execute('UPDATE post_embed SET sub_id = %s WHERE id = %s', (get_value(embed, 'sub_id'), existing_embed['id'],))

    if existing_embed is not None:
        return existing_embed['id']

    with get_cursor() as cursor:
        query = "INSERT INTO post_embed (post_id, subject, description, url, sub_id) VALUES (%s, %s, %s, %s, %s) RETURNING id"
        cursor.execute(query, (post_id, embed['subject'], embed['description'], embed['url'], get_value(embed, 'sub_id')))
        return cursor.fetchone()['id']

def remove_post_files(post_id):
    paths = []
    with get_cursor() as cursor:
        query = 'SELECT * FROM post_file WHERE post_id = %s'
        cursor.execute(query, (post_id,))
        for row in cursor.fetchall():
            preview = get_value(row, 'preview_path')
            if preview is not None:
                paths.append(preview)
            path = get_value(row, 'path')
            if path is not None:
                paths.append(path)

        query = 'SELECT thumbnail_path FROM post WHERE id = %s'
        cursor.execute(query, (post_id,))
        row = cursor.fetchone()
        if row['thumbnail_path'] is not None:
            paths.append(row['thumbnail_path'])

    for path in paths:
        delete_file(path)

def set_and_upload_post_thumbnail_if_needed(file):
    post_id = file['post_id']
    if post_is_missing_thumbnail(post_id) and is_mime_type_image(file['mime_type']):
        thumbnail_path = f'thumbnails/{file["service"]}/{post_id}/thumbnail.jpeg'
        image = make_thumbnail(file['local_path'])
        if image is None:
            current_app.logger.debug(f'Skipping thumbnail for post {post_id} (mime: {file["mime_type"]})')
            return

        (thumbnail_bytes, thumbnail_mime) = image
        upload_file_bytes(thumbnail_path, thumbnail_bytes, thumbnail_mime)
        set_post_thumbnail(post_id, thumbnail_path)

def set_post_content(post_id, content):
    with get_cursor() as cursor:
        cursor.execute("UPDATE post SET content = %s WHERE id = %s", (content, post_id,))

def get_extra_post_content_by_content(post_id, content, title):
    with get_cursor() as cursor:
        query = 'SELECT * FROM extra_post_content WHERE post_id = %s AND content = %s AND title = %s'
        cursor.execute(query, (post_id, content, title,))
        return cursor.fetchone()

def insert_extra_post_content(post_id, content, title, sub_id = None):
    existing_extra_post_content = get_extra_post_content_by_content(post_id, content, title)
    if existing_extra_post_content is not None and get_value(existing_extra_post_content, 'sub_id') != sub_id:
        with get_cursor() as cursor:
            cursor.execute('UPDATE extra_post_content SET sub_id = %s WHERE id = %s', (sub_id, existing_extra_post_content['id']))

    if existing_extra_post_content:
        return existing_extra_post_content['id']

    with get_cursor() as cursor:
        query = 'INSERT INTO extra_post_content (post_id, title, content, sub_id) VALUES (%s, %s, %s, %s) RETURNING id'
        cursor.execute(query, (post_id, title, content, sub_id,))
        return cursor.fetchone()['id']

def delete_post(post_id):
    current_app.logger.debug(f'Deleting post {post_id}')
    try:
        files = []
        with get_cursor() as cursor:
            query = """
                SELECT preview_path path, pf.bucket_name bucket_name FROM post_file pf INNER JOIN post p ON pf.post_id = p.id WHERE p.id = %(post_id)s
                UNION ALL
                SELECT path, pf.bucket_name bucket_name FROM post_file pf INNER JOIN post p ON pf.post_id = p.id WHERE p.id = %(post_id)s
                UNION ALL
                SELECT thumbnail_path path, bucket_name FROM post WHERE id = %(post_id)s
            """
            cursor.execute(query, {'post_id': post_id})
            rows = cursor.fetchall()

        for row in rows:
            if row['path'] is not None:
                delete_file(row['path'], row['bucket_name'])

        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM processed_sub_id WHERE post_id = %s', (post_id,))
            cursor.execute('DELETE FROM account_post_favorite WHERE post_id = %s', (post_id,))
            cursor.execute('DELETE FROM post_file WHERE post_id = %s', (post_id,))
            cursor.execute('DELETE FROM post_embed WHERE post_id = %s', (post_id,))
            cursor.execute('DELETE FROM account_post_favorite WHERE post_id = %s', (post_id,))
            cursor.execute('DELETE FROM extra_post_content WHERE post_id = %s', (post_id,))
            cursor.execute('DELETE FROM post WHERE id = %s', (post_id,))
            conn.commit()
    except Exception:
        current_app.logger.exception(f'Error deleting artist {post_id}')
    current_app.logger.debug(f'Finished deleting artist {post_id}')
    get_total_post_count(True)
    delete_keys('favorite_post_count:*')

def add_post_to_dnp_list(post_id):
    with get_cursor() as cursor:
        post = get_post(post_id, True)
        artist = get_artist(post['artist_id'])
        cursor.execute('INSERT INTO banned_post (service, artist_service_id, post_service_id) VALUES (%s, %s, %s)', (post['service'], artist['service_id'], post['service_id']))

def is_post_dnp(service, artist_service_id, service_id):
    with get_cursor() as cursor:
        cursor.execute('SELECT * FROM banned_post WHERE service = %s AND artist_service_id = %s AND post_service_id = %s', (service, artist_service_id, service_id))
        return cursor.fetchone() is not None

def remove_content_with_sub_id(post_id, sub_id):
    files_to_delete = []

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT preview_path, path, bucket_name FROM post_file WHERE post_id = %s AND sub_id = %s', (post_id, sub_id,))
        for row in cursor.fetchall():
            if row['preview_path'] is not None:
                files_to_delete.append((row['preview_path'], row['bucket_name']))
            files_to_delete.append((row['path'], row['bucket_name']))
        cursor.execute('DELETE FROM post_file WHERE post_id = %s AND sub_id = %s', (post_id, sub_id,))
        cursor.execute('DELETE FROM extra_post_content WHERE post_id = %s AND sub_id = %s', (post_id, sub_id,))
        cursor.execute('DELETE FROM post_embed WHERE post_id = %s AND sub_id = %s', (post_id, sub_id,))
        conn.commit()

    for (path, bucket) in files_to_delete:
        delete_file(path, bucket)
    mark_sub_id_unprocessed(post_id, sub_id)

def is_flagged_for_reimport(service, service_artist_id, service_post_id):
    post_id = get_post_id_from_service_data(service, service_artist_id, service_post_id)
    if post_id is None:
        return False

    with get_cursor() as cursor:
        cursor.execute('SELECT 1 FROM reimport_flag WHERE post_id = %s', (post_id,))
        return cursor.fetchone() is not None

def get_all_processed_sub_ids(service, service_artist_id, service_post_id):
    post_id = get_post_id_from_service_data(service, service_artist_id, service_post_id)
    if post_id is None:
        return []

    with get_cursor() as cursor:
        query = 'SELECT sub_id FROM processed_sub_id WHERE post_id = %s'
        cursor.execute(query, (post_id,))
        return [row['sub_id'] for row in cursor.fetchall()]

def mark_sub_id_unprocessed(post_id, sub_id):
    with get_cursor() as cursor:
        query = 'DELETE FROM processed_sub_id WHERE post_id = %s AND sub_id = %s'
        cursor.execute(query, (post_id, sub_id,))

def mark_sub_id_processed(post_id, sub_id):
    with get_cursor() as cursor:
        query = 'INSERT INTO processed_sub_id (post_id, sub_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id'
        cursor.execute(query, (post_id, sub_id,))
        result = cursor.fetchone()

    if result is None:
        with get_cursor() as cursor:
            query = 'SELECT id FROM processed_sub_id WHERE post_id = %s AND sub_id = %s'
            cursor.execute(query, (post_id, sub_id,))
            result = cursor.fetchone()

    return result['id']
