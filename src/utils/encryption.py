from flask import current_app

import json
import sys
import os
import time
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5 as Cipher_PKCS1_v1_5, AES, PKCS1_OAEP
from base64 import b64decode, b64encode
from os import makedirs
from os.path import join
import uuid

from .logger import log
from .utils import get_config, get_value

def encrypt_and_log_session(import_id, data):
    try:
        service = get_value(data, 'service')
        session_dir = get_config('SESSION_STORAGE_LOCATION')
        makedirs(session_dir, exist_ok = True)
        data = {
            **data,
            'import_id': import_id,
        }
        to_encrypt = json.dumps(data)

        key_der = b64decode(get_config('RSA_PUB_KEY').strip())
        key_pub = RSA.importKey(key_der)
        cipher = Cipher_PKCS1_v1_5.new(key_pub)
        cipher_text = cipher.encrypt(to_encrypt.encode())

        filename = f'{service}-{import_id}'
        to_write = b64encode(cipher_text).decode('utf-8')

        with open(join(session_dir, filename), 'w') as f:
            f.write(to_write)
    except Exception as e:
        log(import_id, f'Error encrypting session data. Continuing with import without saving.', 'exception')

def aes_encrypt_session_key(session_key):
    session_key = session_key.encode('utf-8')
    nonce = make_nonce_from_time()
    aes_key = b64decode(get_config('SESSION_AES_KEY'))
    cipher = AES.new(aes_key, AES.MODE_GCM, nonce = nonce)
    ciphertext, tag = cipher.encrypt_and_digest(session_key)
    return {
        'nonce': b64encode(nonce).decode('ascii'),
        'ciphertext': b64encode(ciphertext).decode('ascii'),
        'tag': b64encode(tag).decode('ascii')
    }

def aes_decrypt_session_key(data):
    nonce = b64decode(data['nonce'].encode('ascii'))
    ciphertext = b64decode(data['ciphertext'].encode('ascii'))
    tag = b64decode(data['tag'].encode('ascii'))

    aes_key = b64decode(get_config('SESSION_AES_KEY'))
    cipher = AES.new(aes_key, AES.MODE_GCM, nonce = nonce)
    plaintext = cipher.decrypt(ciphertext)
    cipher.verify(tag)
    return plaintext.decode('utf-8')

def make_nonce_from_time():
    micro_time = int(time.time_ns() / 1000)
    nonce_bytes = micro_time.to_bytes(8, byteorder = sys.byteorder)
    nonce_bytes += os.urandom(8)
    return nonce_bytes

def rsa_encrypt_session_key(data, key):
    try:
        to_encrypt = json.dumps(data)
        key_der = b64decode(key.strip())
        key_pub = RSA.importKey(key_der)
        cipher = PKCS1_OAEP.new(key_pub)
        cipher_text = cipher.encrypt(to_encrypt.encode())
        return b64encode(cipher_text).decode('utf-8')
    except Exception as e:
        current_app.logger.exception(f'Could not encrypt session: {e}')
    return None

def rsa_decrypt_session_key(id, data, key):
    try:
        key_der = b64decode(key.strip())
        key = RSA.importKey(key_der)
        decoded = b64decode(data)
        decryptor = PKCS1_OAEP.new(key)
        session_data = decryptor.decrypt(decoded).decode('utf-8')
        return json.loads(session_data)
    except Exception as e:
        current_app.logger.exception(f'Could not decrypt session {id}: {e}')
    return None
