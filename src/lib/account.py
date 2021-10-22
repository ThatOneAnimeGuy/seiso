from flask import session, current_app, flash

from ..internals.database.database import get_cursor
from ..utils.utils import get_value
from ..internals.cache.redis import get_redis, serialize, deserialize
from ..lib.security import is_login_rate_limited
from .artist import get_artist

import bcrypt
import base64
import hashlib

def load_account(account_id = None, reload = False):
    if account_id is None and 'account_id' in session:
        return load_account(session['account_id'], reload)
    elif account_id is None and 'account_id' not in session:
        return None

    redis = get_redis()
    key = f'account_v3:{account_id}'
    account = redis.get(key)
    if account is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT id, username, display_name, created_at FROM account WHERE id = %s'
            cursor.execute(query, (account_id,))
            account = cursor.fetchone()
            if account is not None:
                query = 'SELECT role FROM account_role WHERE account_id = %s'
                cursor.execute(query, (account_id,))
                account['roles'] = [row['role'] for row in cursor.fetchall()]

        redis.set(key, serialize(account))
    else:
        account = deserialize(account)

    return account

def get_login_info_for_username(username):
    with get_cursor() as cursor:
        query = 'SELECT id, password_hash FROM account WHERE username = %s'
        cursor.execute(query, (username,))
        return cursor.fetchone()

def is_logged_in():
    if 'account_id' in session:
        return True
    return False

def is_username_taken(username):
    with get_cursor() as cursor:
        query = 'SELECT id FROM account WHERE username = %s'
        cursor.execute(query, (username,))
        return cursor.fetchone() is not None

def create_account(username, password):
    password_hash = bcrypt.hashpw(get_base_password_hash(password), bcrypt.gensalt()).decode('utf-8')

    with get_cursor() as cursor:
        query = "INSERT INTO account (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING RETURNING id"
        cursor.execute(query, (username, password_hash,))
        row = cursor.fetchone()
        if row is None:
            return False
    return True

def change_password(account_id, password):
    password_hash = bcrypt.hashpw(get_base_password_hash(password), bcrypt.gensalt()).decode('utf-8')

    with get_cursor() as cursor:
        query = "UPDATE account SET password_hash = %s WHERE id = %s"
        cursor.execute(query, (password_hash, account_id,))

def check_password(username, password):
    if username is None or password is None:
        return False

    account_info = get_login_info_for_username(username)
    if account_info is None:
        return False

    if get_value(current_app.config, 'ENABLE_LOGIN_RATE_LIMITING') and is_login_rate_limited(account_info['id']):
        flash('You\'re doing that too much. Try again in a little bit.')
        return False

    if bcrypt.checkpw(get_base_password_hash(password), account_info['password_hash'].encode('utf-8')):
        return True

    flash('Password is incorrect')
    return False

def attempt_login(username, password):
    if username is None or password is None:
        return False

    account_info = get_login_info_for_username(username)
    if account_info is None:
        flash('Username or password is incorrect')
        return False

    if get_value(current_app.config, 'ENABLE_LOGIN_RATE_LIMITING') and is_login_rate_limited(account_info['id']):
        flash('You\'re doing that too much. Try again in a little bit.')
        return False

    if bcrypt.checkpw(get_base_password_hash(password), account_info['password_hash'].encode('utf-8')):
        account = load_account(account_info['id'], True)
        session['account_id'] = account['id']
        return True

    flash('Username or password is incorrect')
    return False

def get_base_password_hash(password):
    return base64.b64encode(hashlib.sha256(password.encode('utf-8')).digest())

def get_artists_that_account_supports(account_id, service):
    with get_cursor() as cursor:
        query = """
            SELECT artist_id
            FROM account_artist_subscription aas
            INNER JOIN artist a ON a.id = aas.artist_id
            WHERE
                aas.account_id = %s
                AND
                a.service = %s
        """
        cursor.execute(query, (account_id, service,))
        return [row['artist_id'] for row in cursor.fetchall()]

def upsert_account_supports_artist(account_id, artist_id, was_present_in_most_recent_import):
    # Technically a race condition but it's too unlikely to worry about
    if get_artist(artist_id) is None:
        return

    with get_cursor() as cursor:
        if was_present_in_most_recent_import:
            current_app.logger.debug(f'Upserting artist {artist_id} for account {account_id}')
            query = """
                INSERT INTO account_artist_subscription (account_id, artist_id, was_present_in_most_recent_import, last_imported_at)
                VALUES (%s, %s, %s, (now() at time zone 'utc'))
                ON CONFLICT (account_id, artist_id) DO
                    UPDATE SET was_present_in_most_recent_import = true, last_imported_at = (now() at time zone 'utc')
            """
            cursor.execute(query, (account_id, artist_id, was_present_in_most_recent_import,))
        else:
            current_app.logger.debug(f'Updating artist {artist_id} for account {account_id}')
            query = 'UPDATE account_artist_subscription SET was_present_in_most_recent_import = false WHERE account_id = %s AND artist_id = %s'
            cursor.execute(query, (account_id, artist_id,))

def mark_account_as_subscribed_to_artists(account_id, artist_ids, service):
    current_app.logger.debug(f'Marking that account {account_id} is subscribed to {artist_ids}')
    existing_ids = get_artists_that_account_supports(account_id, service)
    current_app.logger.debug(f'Account {account_id} has existing ids {existing_ids}')
    for artist_id in existing_ids:
        if artist_id not in artist_ids:
            upsert_account_supports_artist(account_id, artist_id, False)

    for artist_id in artist_ids:
        upsert_account_supports_artist(account_id, artist_id, True)

def get_account_stats(account_id, reload = False):
    redis = get_redis()
    key = f'account_stats:{account_id}'
    stats = redis.get(key)
    if stats is None or reload:
        stats = {
            'artists_imported': 0,
            'artist_favorites': 0,
            'posts_imported': 0,
        }

        with get_cursor() as cursor:
            query = 'SELECT count(*) count FROM account_artist_subscription aas INNER JOIN artist a ON aas.artist_id = a.id LEFT JOIN do_not_post_request dnpr ON a.service = dnpr.service AND a.service_id = dnpr.service_id WHERE aas.account_id = %s AND dnpr.id IS NULL'
            cursor.execute(query, (account_id,))
            count = cursor.fetchone()['count']
            stats['artists_imported'] = count

            query = 'SELECT count(*) count FROM account_artist_subscription aas INNER JOIN account_artist_favorite aaf ON aas.artist_id = aaf.artist_id WHERE aas.account_id = %s'
            cursor.execute(query, (account_id,))
            count = cursor.fetchone()['count']
            stats['artist_favorites'] = count

            query = 'SELECT count(*) FROM post p INNER JOIN account_artist_subscription aas ON p.artist_id = aas.artist_id WHERE aas.account_id = %s AND (p.published_at <= aas.last_imported_at OR p.added_at <= aas.last_imported_at)'
            cursor.execute(query, (account_id,))
            count = cursor.fetchone()['count']
            stats['posts_imported'] = count

        redis.set(key, serialize(stats), ex = 3600)
    else:
        stats = deserialize(stats)
    return stats

def is_admin(account):
    roles = account['roles']
    if 'admin' in roles:
        return True
    return False

def get_account_display_name(account_id):
    account = load_account(account_id)
    if account is None:
        return None
    if account['display_name'] is None:
        return 'Anonymous'
    return account['display_name']

def get_all_account_ids_with_imports():
    with get_cursor() as cursor:
        query = 'SELECT distinct(account_id) account_id FROM account_artist_subscription aas WHERE EXISTS(SELECT * FROM post p WHERE p.artist_id = aas.artist_id)'
        cursor.execute(query)
        return [row['account_id'] for row in cursor.fetchall()]

def is_display_name_taken(display_name):
    with get_cursor() as cursor:
        query = 'SELECT id FROM account WHERE display_name = %s'
        cursor.execute(query, (display_name,))
        return cursor.fetchone() is not None

def change_display_name(account_id, display_name):
    with get_cursor() as cursor:
        query = 'UPDATE account SET display_name = %s WHERE id = %s'
        cursor.execute(query, (display_name, account_id,))
    load_account(account_id, True)

def get_account_auto_imports(account_id, reload = False):
    redis = get_redis()
    key = f'account_auto_imports:{account_id}'
    imports = redis.get(key)
    if imports is None or reload:
        imports = []
        with get_cursor() as cursor:
            query = 'SELECT * FROM account_session WHERE account_id = %s'
            cursor.execute(query, (account_id,))
            for row in cursor.fetchall():
                imports.append({
                    'service': row['service'],
                    'retries_remaining': row['retries_remaining'],
                    'created_at': row['created_at'],
                    'last_imported_at': row['last_imported_at']
                })
        redis.set(key, serialize(imports))
    else:
        imports = deserialize(imports)
    return imports
