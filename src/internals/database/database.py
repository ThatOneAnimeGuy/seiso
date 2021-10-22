import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

from ...utils.utils import get_config

pool = None

def init():
    global pool
    try:
        pool = psycopg2.pool.ThreadedConnectionPool(1, 2000,
            host = get_config('DATABASE_HOST'),
            dbname = get_config('DATABASE_NAME'),
            user = get_config('DATABASE_USER'),
            password = get_config('DATABASE_PASSWORD'),
            port = get_config('DATABASE_PORT', 5432),
            cursor_factory = RealDictCursor
        )
    except Exception as error:
        print("Failed to connect to the database: ", error)

@contextmanager
def get_conn(key = None):
    try:
        with pool.getconn(key) as conn:
            conn.autocommit = False
            yield conn
    except:
        raise
    finally:
        pool.putconn(conn, key)

@contextmanager
def get_cursor(key = None):
    try:
        with pool.getconn(key) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                yield cur
    except:
        raise
    finally:
        pool.putconn(conn, key)
