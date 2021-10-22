import requests
import hashlib
from redis_rate_limit import RateLimit, TooManyRequests

from ..internals.cache.redis import get_pool

from flask import current_app

def is_password_compromised(password):
    h = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
    first_five = h[0:5]
    rest = h[5:]

    try:
        resp = requests.get('https://api.pwnedpasswords.com/range/' + first_five)
        if rest in resp.text:
            return True
    except Exception as e:
        current_app.logger.exception('Error calling pwnedpasswords API: ' + str(e))
        return False

    return False

def is_login_rate_limited(account_id):
    pool = get_pool()
    try:
        with RateLimit(resource='login', client=str(account_id), max_requests=5, expire=300, redis_pool=pool):
            return False
    except TooManyRequests:
        return True
