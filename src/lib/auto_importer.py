from flask import current_app

from ..internals.database.database import get_cursor
from ..utils.utils import sha256, get_config, get_import_id
from ..utils.encryption import rsa_encrypt_session_key, rsa_decrypt_session_key
from ..lib.account import get_account_auto_imports
from ..lib import importer

def start_all_auto_imports(private_key):
    rows = []
    with get_cursor() as cursor:
        query = 'SELECT * FROM account_session WHERE retries_remaining > 0 AND last_imported_at < (\'now\'::timestamp - \'23 hours 55 minutes\'::interval)'
        cursor.execute(query)
        rows = cursor.fetchall()
    for row in rows:
        try:
            account_session_id = row['id']
            service = row['service']
            account_id = row['account_id']
            encrypted_key = row['encrypted_key']

            key = rsa_decrypt_session_key(account_session_id, encrypted_key, private_key)
            if key is None:
                continue

            import_id = get_import_id(key)
            importer.start_import(service, key, import_id, account_id)
            current_app.logger.debug(f'Starting import {import_id} to {service}')
            mark_session_imported_now(key, service, account_id)
        except:
            current_app.logger.exception(f'Error starting import using key {account_session_id}')
            continue

def mark_session_imported_now(session_key, service, account_id):
    sha256_hash = sha256(session_key.encode('utf-8'))
    with get_cursor() as cursor:
        query = "UPDATE account_session SET last_imported_at = (now() at time zone 'utc') WHERE session_key_sha256_hash = %s AND service = %s"
        cursor.execute(query, (sha256_hash, service,))
    get_account_auto_imports(account_id, True)

def decrease_session_retries_remaining(session_key, service, account_id):
    sha256_hash = sha256(session_key.encode('utf-8'))
    with get_cursor() as cursor:
        query = 'UPDATE account_session SET retries_remaining = retries_remaining - 1 WHERE session_key_sha256_hash = %s AND service = %s'
        cursor.execute(query, (sha256_hash, service,))
    get_account_auto_imports(account_id, True)

def save_session_for_auto_import(service, session_key, account_id):
    if account_id is None:
        return

    encrypted_key = rsa_encrypt_session_key(session_key, get_config('RSA_PUB_KEY'))
    sha256_hash = sha256(session_key.encode('utf-8'))
    with get_cursor() as cursor:
        query = '''
            INSERT INTO account_session
                (account_id, service, encrypted_key, session_key_sha256_hash, retries_remaining) VALUES (%s, %s, %s, %s, 2)
            ON CONFLICT (account_id, service) DO
                UPDATE SET
                    encrypted_key = EXCLUDED.encrypted_key,
                    session_key_sha256_hash = EXCLUDED.session_key_sha256_hash,
                    retries_remaining = 2,
                    last_imported_at = (now() at time zone 'utc'),
                    created_at = (now() at time zone 'utc')
                WHERE account_session.session_key_sha256_hash != EXCLUDED.session_key_sha256_hash
            RETURNING id
        '''
        cursor.execute(query, (account_id, service, encrypted_key, sha256_hash,))
        new_id = cursor.fetchone()
        if new_id is None:
            return False
        get_account_auto_imports(account_id, True)
        return True

def delete_sessions_for_service(service, account_id):
    with get_cursor() as cursor:
        query = 'DELETE FROM account_session WHERE service = %s AND account_id = %s'
        cursor.execute(query, (service, account_id,))
    get_account_auto_imports(account_id, True)
