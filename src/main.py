import re
import datetime
import uwsgi
from yoyo import read_migrations
from yoyo import get_backend
from datetime import timedelta
from os import getenv
import os
from os.path import join, dirname

import logging
from flask import Flask, render_template, request, redirect, g, abort, session

import src.internals.database.database as database
import src.internals.cache.redis as redis
from src.lib.ab_test import get_all_variants
from src.lib.account import is_logged_in
from src.utils.utils import url_is_for_non_logged_file_extension, render_page_data, get_config, get_value, make_template, cdn, has_preview, make_background_image, pluralify, url_encode, pluralify_word, service_to_display_name
from src.utils.import_lock import clear_lock_table
from src.utils.download import initialize_temp_download_directory
from src.lib.importer import restart_stopped_imports
from src.utils.startup_tasks import clear_startup_lock, run_startup_tasks

from src.app.pages.root import root
from src.app.pages.artists import artists
from src.app.pages.random import random
from src.app.pages.post import post
from src.app.pages.account import account
from src.app.pages.favorites import favorites
from src.app.pages.help import help_app
from src.app.pages.support import support
from src.app.pages.importer import importer_page
from src.app.pages.requests import requests
from src.app.pages.dmca import dmca
from src.app.pages.leaderboard import leaderboard

app = Flask(
    __name__,
    template_folder='app/views'
)

app.url_map.strict_slashes = False

app.register_blueprint(root)
app.register_blueprint(artists)
app.register_blueprint(random)
app.register_blueprint(post)
app.register_blueprint(account)
app.register_blueprint(favorites)
app.register_blueprint(support)
app.register_blueprint(importer_page)
app.register_blueprint(requests)
app.register_blueprint(dmca)
app.register_blueprint(leaderboard)
app.register_blueprint(help_app, url_prefix='/help')

app.jinja_env.globals.update(is_logged_in=is_logged_in)
app.jinja_env.globals.update(render_page_data=render_page_data)
app.jinja_env.globals.update(get_value=get_value)
app.jinja_env.globals.update(cdn=cdn)
app.jinja_env.globals.update(has_preview=has_preview)
app.jinja_env.globals.update(make_background_image=make_background_image)
app.jinja_env.globals.update(pluralify=pluralify)
app.jinja_env.globals.update(pluralify_word=pluralify_word)
app.jinja_env.globals.update(url_encode=url_encode)
app.jinja_env.globals.update(service_to_display_name=service_to_display_name)
app.jinja_env.filters['regex_match'] = lambda val, rgx: re.search(rgx, val)
app.jinja_env.filters['regex_find'] = lambda val, rgx: re.findall(rgx, val)

app.config.from_pyfile('../config.py')

logging.getLogger('PIL').setLevel(logging.INFO)
logging.getLogger('requests').setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.INFO)
logging.getLogger('botocore').setLevel(logging.INFO)
logging.getLogger('s3transfer').setLevel(logging.INFO)

with app.app_context():
    logging.basicConfig(filename=get_config('LOG_LOCATION'), level=logging.DEBUG)

    if uwsgi.worker_id() == 0:
        clear_startup_lock()
        initialize_temp_download_directory()
        backend = get_backend('postgres://' + get_config('DATABASE_USER') + ':' + get_config('DATABASE_PASSWORD') + '@' + get_config('DATABASE_HOST') + '/' + get_config('DATABASE_NAME'))
        migrations = read_migrations('./migrations')
        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))

@app.before_first_request
def do_app_init_stuff():
    database.init()
    redis.init()
    run_startup_tasks(clear_lock_table, restart_stopped_imports)

@app.before_request
def do_request_init_stuff():
    g.page_data = {}
    g.data = {}
    g.request_start_time = datetime.datetime.now()
    session.permanent = True
    session.modified = False
    app.permanent_session_lifetime = timedelta(days=30)

@app.after_request
def do_finish_stuff(response):
    if not url_is_for_non_logged_file_extension(request.path):
        start_time = g.request_start_time
        end_time = datetime.datetime.now()
        elapsed = end_time - start_time
        app.logger.debug('[{4}] Completed {0} request to {1} in {2}ms with ab test variants: {3}'.format(request.method, request.url, elapsed.microseconds/1000, get_all_variants(), end_time.strftime("%Y-%m-%d %X")))
    response.autocorrect_location_header = False
    return response
