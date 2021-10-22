import uwsgi
import os

from .utils import get_config

def get_startup_lock():
    try:
        uwsgi.lock()
        if os.path.isfile(get_config('STARTUP_TASKS_LOCK_FILE')):
            return False
        else:
            open(get_config('STARTUP_TASKS_LOCK_FILE'), 'w').close()
            return True
    finally:
        uwsgi.unlock()
    return False

def clear_startup_lock():
    if os.path.isfile(get_config('STARTUP_TASKS_LOCK_FILE')):
        os.remove(get_config('STARTUP_TASKS_LOCK_FILE'))

def run_startup_tasks(*funcs):
    success = get_startup_lock()
    if success:
        for func in funcs:
            func()
