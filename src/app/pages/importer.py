from flask import Blueprint, request, make_response, render_template, current_app, g, flash, redirect, url_for

import json

from ...lib.importer import start_import, is_import_ongoing
from ...lib.auto_importer import start_all_auto_imports, save_session_for_auto_import
from ...utils import logger
from ...utils.utils import get_import_id, make_template, get_value, parse_int
from ...utils.encryption import encrypt_and_log_session
from ...lib.account import load_account

importer_page = Blueprint('importer_page', __name__)

@importer_page.route('/importer')
def get_importer():
    return make_template('importer/index.html', 200)

@importer_page.route('/importer/tutorial')
def importer_tutorial():
    return make_template('importer/tutorial.html', 200)

@importer_page.route('/importer/status/<import_id>')
def importer_status(import_id):
    g.page_data['import_id'] = import_id

    return make_template('importer/status.html', 200)

@importer_page.route('/api/logs/<import_id>', methods=['GET'])
def get_logs(import_id):
    response = 200
    if not is_import_ongoing(import_id):
        response = 207
    logs = logger.get_logs(import_id)
    return json.dumps(logs), response

@importer_page.route('/api/import', methods=['POST'])
def importer_submit():
    script_header = get_value(request.headers, 'X-Source-Script')
    key = get_value(request.form, 'session_key', '').strip()
    import_id = get_import_id(key)
    service = request.form.get('service')
    allowed_to_save_session = get_value(request.form, 'log_session_key', False)
    allows_auto_import = get_value(request.form, 'allow_auto_import', False)

    account = load_account()

    if not key:
        flash('You must provide a session key')
        return redirect(url_for('importer_page.get_importer'))

    if len(key) > 512:
        flash('Session key too long')
        return redirect(url_for('importer_page.get_importer'))

    if script_header is not None:
        current_app.logger.debug(f'Starting import from script: {script_header}')

    if key and service and (allowed_to_save_session or allows_auto_import):
        data = {
            'service': service,
            'key': key,
            'account_id': get_value(account, 'id')
        }
        encrypt_and_log_session(import_id, data)

    if allows_auto_import:
        save_session_for_auto_import(service, key, get_value(account, 'id'))

    start_import(service, key, import_id, get_value(account, 'id'))

    return redirect(url_for('importer_page.importer_status', import_id=import_id))

@importer_page.route('/api/start_auto_imports', methods=['POST'])
def post_start_auth_import():
    private_key = get_value(request.form, 'private_key').strip()
    if private_key is None:
        return 'private key required', 401
    start_all_auto_imports(private_key)
    return '', 204
