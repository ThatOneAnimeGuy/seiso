from flask import current_app

from ..internals.database.database import get_cursor

def take_lock(service, artist_service_id, post_service_id):
    query = 'INSERT INTO post_import_lock (service, artist_service_id, post_service_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING id'
    with get_cursor() as cursor:
        cursor.execute(query, (service, artist_service_id, post_service_id,))
        result = cursor.fetchone()
        if result is None:
            return None
        return result['id']

def release_lock(lock_id):
    try:
        query = 'DELETE FROM post_import_lock WHERE id = %s'
        with get_cursor() as cursor:
            cursor.execute(query, (lock_id,))
    except:
        current_app.logger.exception(f'Could not release post import lock {lock_id}')

def clear_lock_table():
    query = 'DELETE FROM post_import_lock'
    with get_cursor() as cursor:
        cursor.execute(query)
