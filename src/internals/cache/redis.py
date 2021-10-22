import redis
from os import getenv
import dateutil
import datetime
import pickle

from ...utils.utils import get_config

pool = None

def init():
    global pool
    pool = redis.ConnectionPool(host=get_config('REDIS_HOST'), port=get_config('REDIS_PORT'), password=get_config('REDIS_PASSWORD', ''))
    return pool

def get_pool():
    global pool
    return pool

def get_redis():
    return redis.Redis(connection_pool=pool)

def delete_keys(pattern):
    redis = get_redis()
    keys = redis.keys(pattern)
    if len(keys) > 0:
        redis.delete(*keys)

def delete_key_list(keys):
    conn = get_redis()
    for key in keys:
        conn.delete(key)

def serialize(data):
    return pickle.dumps(data)

def deserialize(data):
    return pickle.loads(data)
