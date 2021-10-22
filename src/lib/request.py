from ..internals.database.database import get_cursor
from ..internals.cache.redis import get_redis, serialize, deserialize, delete_keys

def get_requests_for_list(offset):
    redis = get_redis()
    key = f'request_list:{offset}'
    requests = redis.get(key)
    if requests is None:
        with get_cursor() as cursor:
            query = 'SELECT * FROM request ORDER BY id DESC OFFSET %s LIMIT 25'
            cursor.execute(query, (offset,))
            requests = cursor.fetchall()
        redis.set(key, serialize(requests))
    else:
        requests = deserialize(requests)
    return requests

def get_requests_search_results(status, service, sort_by, sort_direction, max_price):
    cursor = get_cursor()
    query = ''

def get_request(request_id, reload = False):
    redis = get_redis()
    key = f'request:{request_id}'
    request = redis.get(key)
    if request is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT * FROM request WHERE id = %s'
            cursor.execute(query, (request_id,))
            request = cursor.fetchall()
        redis.set(key, serialize(request))
    else:
        request = deserialize(request)
    return request

def ip_has_voted_for_request_already(request_id, ip_address):
    with get_cursor() as cursor:
        query = 'SELECT 1 FROM request_vote WHERE request_id = %s AND ip_address = %s'
        cursor.execute(query, (request_id, ip_address,))
        return cursor.fetchone() is not None

def insert_request():
    with get_cursor() as cursor:
        query = 'INSERT INTO request (service, service_id, title, description, image_path, price, status) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id'
        cursor.execute(query, (service, service_id, title, description, image_path, price, status,))
        if cursor.fetchone() is None:
            return False

    delete_keys('request_list:*')
    return True

def insert_request_vote(request_id, ip_address):
    exists = False
    with get_cursor() as cursor:
        cursor.execute('INSERT INTO request_vote (request_id, ip_address) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id', (request_id, ip_address,))
        if cursor.fetchone() is not None:
            cursor.execute('UPDATE request SET votes = votes + 1 WHERE id = %s', (request_id,))
            exists = True

    if exists:
        get_request(request_id, True)

def get_total_request_count(reload = False):
    redis = get_redis()
    key = f'request_count'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = "SELECT count(*) as count FROM request WHERE status = 'open'"
            cursor.execute(query)
            count = cursor.fetchone()['count']
        redis.set(key, serialize(count))
    else:
        count = deserialize(count)
    return count
