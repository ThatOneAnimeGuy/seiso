from flask import current_app

import ujson
import uwsgi
import os

from ..importer.importers import patreon
from ..importer.importers import fanbox
from ..importer.importers import fantia
from ..internals.database.database import get_cursor
from ..utils.utils import sha256, get_value, get_config, get_import_id
from ..utils.logger import log
from ..utils.encryption import aes_encrypt_session_key, aes_decrypt_session_key
from ..utils.flask_thread import FlaskThread
from .account import get_account_stats

def import_posts(target, import_id, key, service, account_id, override_collision):
    should_start_import = False
    try:
        (is_collision, ongoing_import_id) = mark_import_as_ongoing(import_id, key, service, account_id)
        should_start_import = (not is_collision or override_collision) and ongoing_import_id
        if should_start_import:
            target(import_id, key, account_id)
        else:
            log(import_id, 'This session key is already being imported in the background')
    except:
        log(import_id, 'Internal error. Contact site staff on Telegram.', 'exception')
    finally:
        if should_start_import:
            mark_import_as_complete(ongoing_import_id)
    if account_id is not None:
        get_account_stats(account_id, True)
        log(import_id, 'Check your import stats in your account page!')
        log(import_id, 'Your import leaderboard score will update within the next two hours')
    else:
        log(import_id, 'Register for an account to get credit for your next import!')

def mark_import_as_ongoing(import_id, session_key, service, account_id):
    query = 'INSERT INTO ongoing_import (import_id, service, encrypted_session_key, session_key_sha256_hash, account_id) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id'
    encrypted_data = ujson.dumps(aes_encrypt_session_key(session_key))
    sha256_hash = sha256(session_key.encode('utf-8'))
    with get_cursor() as cursor:
        cursor.execute(query, (import_id, service, encrypted_data, sha256_hash, account_id))
        result = cursor.fetchone()
        if result is None:
            return (True, get_ongoing_import_id_by_hash(sha256_hash))
        return (False, result['id'])

def mark_import_as_complete(ongoing_import_id):
    try:
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM ongoing_import WHERE id = %s', (ongoing_import_id,))
    except:
        current_app.logger.exception(f'Unable to remove ongoing import {ongoing_import_id}')

def get_ongoing_import_id_by_hash(hash):
    query = 'SELECT id FROM ongoing_import WHERE session_key_sha256_hash = %s'
    with get_cursor() as cursor:
        cursor.execute(query, (hash,))
        return get_value(cursor.fetchone(), 'id')

def get_ongoing_import_session_keys():
    keys = []
    rows = []
    query = 'SELECT id, encrypted_session_key, import_id, service, account_id FROM ongoing_import'
    with get_cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    for row in rows:
        try:
            data = ujson.loads(row['encrypted_session_key'])
            key = aes_decrypt_session_key(data)
            keys.append({
                'key': key,
                'import_id': row['import_id'],
                'service': row['service'],
                'account_id': row['account_id']
            })
        except:
            current_app.logger.exception(f'Failed to decrypt session key: {data}')
            mark_import_as_complete(row['id'])
    return keys

def is_import_ongoing(import_id):
    query = 'SELECT id FROM ongoing_import WHERE import_id = %s'
    with get_cursor() as cursor:
        cursor.execute(query, (import_id,))
        return cursor.fetchone() is not None

def restart_stopped_imports():
    current_app.logger.debug('Restarting stopped imports')
    import_data = get_ongoing_import_session_keys()
    for key in import_data:
        log(key['import_id'], 'Restarting import due to server reboot')
        start_import(key['service'], key['key'], key['import_id'], key['account_id'], True)

def start_import(service, key, import_id, account_id, override_collision = False):
    target = None
    if service == 'patreon':
        target = patreon.import_posts
    elif service == 'fanbox':
        target = fanbox.import_posts
    elif service == 'fantia':
        target = fantia.import_posts

    if target and key:
        log(import_id, f'Starting import. Your import id is {import_id}')
        FlaskThread(target=import_posts, args=(target, import_id, key, service, account_id, override_collision,)).start()
    else:
        log(import_id, f'Error starting import. Your import id was {import_id}')
