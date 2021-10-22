from ..internals.database.database import get_cursor
from ..utils.utils import get_value
from ..internals.cache.redis import get_redis, serialize, deserialize, delete_keys
from ..lib.artist import get_artist
from ..lib.post import get_post_for_listing

import ujson
import copy

def get_favorite_artists(account_id, offset, sort_field, sort_direction):
    if sort_field == 'id':
        sort_field = 'aaf.id'

    with get_cursor() as cursor:
        query = f"""
            SELECT artist_id
            FROM account_artist_favorite aaf
            INNER JOIN artist a ON aaf.artist_id = a.id
            WHERE account_id = %s
            ORDER BY {sort_field} {sort_direction}
            OFFSET %s
            LIMIT 25
        """
        cursor.execute(query, (account_id, offset,))
        favorites = cursor.fetchall()

    artists = []
    for favorite in favorites:
        artist = get_artist(favorite['artist_id'])
        if artist is not None:
            artists.append(artist)
    return artists

def get_favorite_posts(account_id, offset, sort_field, sort_direction):
    if sort_field == 'id':
        sort_field = 'apf.id'

    with get_cursor() as cursor:
        query = f"""
            SELECT post_id
            FROM account_post_favorite apf
            INNER JOIN post p ON apf.post_id = p.id
            WHERE account_id = %s
            ORDER BY {sort_field} {sort_direction}
            OFFSET %s
            LIMIT 25
        """
        cursor.execute(query, (account_id, offset,))
        favorites = cursor.fetchall()

    posts = []
    for favorite in favorites:
        post = get_post_for_listing(favorite['post_id'])
        if post is not None:
            posts.append(post)
    return posts

def get_favorite_post_count(account_id, reload = False):
    redis = get_redis()
    key = f'favorite_post_count:{account_id}'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = "SELECT count(*) as count FROM account_post_favorite WHERE account_id = %s"
            cursor.execute(query, (account_id,))
            count = cursor.fetchone()['count']
        redis.set(key, serialize(count))
    else:
        count = deserialize(count)
    return count

def get_favorite_artist_count(account_id, reload = False):
    redis = get_redis()
    key = f'favorite_artist_count:{account_id}'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = "SELECT count(*) as count FROM account_artist_favorite WHERE account_id = %s"
            cursor.execute(query, (account_id,))
            count = cursor.fetchone()['count']
        redis.set(key, serialize(count))
    else:
        count = deserialize(count)
    return count

def is_artist_favorited(account_id, artist_id, reload = False):
    redis = get_redis()
    key = f'artist_favorited:{account_id}:{artist_id}'
    value = redis.get(key)
    if value is None or reload:
        with get_cursor() as cursor:
            query = "SELECT 1 FROM account_artist_favorite WHERE account_id = %s AND artist_id = %s"
            cursor.execute(query, (account_id, artist_id,))
            value = cursor.fetchone() is not None
        redis.set(key, serialize(value))
    else:
        value = deserialize(value)
    return value

def is_post_favorited(account_id, post_id, reload = False):
    redis = get_redis()
    key = f'post_favorited:{account_id}:{post_id}'
    value = redis.get(key)
    if value is None or reload:
        with get_cursor() as cursor:
            query = "SELECT 1 FROM account_post_favorite WHERE account_id = %s AND post_id = %s"
            cursor.execute(query, (account_id, post_id,))
            value = cursor.fetchone() is not None
        redis.set(key, serialize(value))
    else:
        value = deserialize(value)
    return value

def get_posts_by_favorited_artists(account_id, offset):
    posts = []
    with get_cursor() as cursor:
        query = """
            SELECT p.id as post_id
            FROM post p
            INNER JOIN account_artist_favorite aaf
                ON p.artist_id = aaf.artist_id
            WHERE
                aaf.account_id = %s
                AND
                p.is_import_finished = true
            ORDER BY p.published_at DESC
            OFFSET %s
            LIMIT 25
        """
        cursor.execute(query, (account_id, offset,))
        rows = cursor.fetchall()

    for row in rows:
        post = get_post_for_listing(row['post_id'])
        if post is not None:
            posts.append(post)

    return posts

def get_count_of_posts_by_favorite_artists(account_id):
     with get_cursor() as cursor:
        query = 'SELECT count(*) as count FROM post p INNER JOIN account_artist_favorite aaf ON p.artist_id = aaf.artist_id WHERE aaf.account_id = %s'
        cursor.execute(query, (account_id,))
        return cursor.fetchone()['count']

def add_favorite_artist(account_id, artist_id):
    with get_cursor() as cursor:
        query = 'INSERT INTO account_artist_favorite (account_id, artist_id) VALUES (%s, %s) ON CONFLICT (account_id, artist_id) DO NOTHING'
        cursor.execute(query, (account_id, artist_id,))
    get_favorite_artist_count(account_id, True)
    is_artist_favorited(account_id, artist_id, True)

def add_favorite_post(account_id, post_id):
    with get_cursor() as cursor:
        query = 'INSERT INTO account_post_favorite (account_id, post_id) VALUES (%s, %s) ON CONFLICT (account_id, post_id) DO NOTHING'
        cursor.execute(query, (account_id, post_id,))
    get_favorite_post_count(account_id, True)
    is_post_favorited(account_id, post_id, True)

def remove_favorite_artist(account_id, artist_id):
    with get_cursor() as cursor:
        query = 'DELETE FROM account_artist_favorite WHERE account_id = %s AND artist_id = %s'
        cursor.execute(query, (account_id, artist_id,))
    get_favorite_artist_count(account_id, True)
    is_artist_favorited(account_id, artist_id, True)

def remove_favorite_post(account_id, post_id):
    with get_cursor() as cursor:
        query = 'DELETE FROM account_post_favorite WHERE account_id = %s AND post_id = %s'
        cursor.execute(query, (account_id, post_id,))
    get_favorite_post_count(account_id, True)
    is_post_favorited(account_id, post_id, True)
