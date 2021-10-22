from flask import Blueprint, request, make_response, render_template, session, redirect, flash, url_for, current_app, g

import urllib
import json

from ...utils.utils import get_value, make_template
from ...lib.account import load_account, is_username_taken, attempt_login, create_account, get_account_stats, change_password, check_password, is_display_name_taken, change_display_name, get_account_auto_imports
from ...lib.security import is_password_compromised
from ...lib.auto_importer import delete_sessions_for_service

account = Blueprint('account', __name__)

@account.route('/account/login', methods=['GET'])
def get_login():
    account = load_account()
    if account is not None:
        return redirect(url_for('artists.get_list'))

    query = request.query_string.decode('utf-8')
    if len(query) > 0:
        g.data['query_string'] = '?' + query

    return make_template('account/login.html', 200)

@account.route('/account/login', methods=['POST'])
def post_login():
    account = load_account()
    if account is not None:
        return redirect(url_for('artists.get_list'))

    query = request.query_string.decode('utf-8')
    if len(query) > 0:
        query = '?' + query

    username = get_value(request.form, 'username')
    password = get_value(request.form, 'password')
    success = attempt_login(username, password)
    if not success:
        return redirect(url_for('account.get_login') +  query)

    redir = get_value(request.args, 'redir')
    if redir is not None:
        return redirect(redir)

    return redirect(url_for('artists.get_list'))

@account.route('/account/logout', methods=['GET', 'POST'])
def logout():
    if 'account_id' in session:
        session.pop('account_id')
    return redirect(url_for('artists.get_list'))

@account.route('/account/register', methods=['GET'])
def get_register():
    account = load_account()
    if account is not None:
        return redirect(url_for('artists.get_list'))

    query = request.query_string.decode('utf-8')
    if len(query) > 0:
        g.data['query_string'] = '?' + query

    return make_template('account/register.html', 200)

@account.route('/account/register', methods=['POST'])
def post_register():
    query = request.query_string.decode('utf-8')
    if len(query) > 0:
        g.data['query_string'] = '?' + query

    username = get_value(request.form, 'username')
    password = get_value(request.form, 'password')
    confirm_password = get_value(request.form, 'confirm_password')

    errors = False
    if len(username) > 30:
        flash('Username is too long')
        errors = True

    if username.strip() == '':
        flash('Username cannot be empty')
        errors = True

    if password.strip() == '':
        flash('Password cannot be empty')
        errors = True

    if password != confirm_password:
        flash('Passwords do not match')
        errors = True

    if is_username_taken(username):
        flash('Username already taken')
        errors = True

    if get_value(current_app.config, 'ENABLE_PASSWORD_VALIDATOR', False) and is_password_compromised(password):
        flash('We\'ve detected that password was compromised in a data breach on another site. Please choose a different password.')
        errors = True

    if not errors:
        success = create_account(username, password)
        if not success:
            flash('Username already taken')
            errors = True

    if not errors:
        account = attempt_login(username, password)
        if account is None:
            current_app.logger.warning('Error logging into account immediately after creation')
        flash('Account created successfully')

        redir = get_value(request.args, 'redir')
        if redir is not None:
            return redirect(redir)

        return redirect(url_for('account.get_account'))

    return make_template('account/register.html', 200)

@account.route('/account', methods=['GET'])
def get_account():
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))

    g.data['account'] = account
    g.data['stats'] = get_account_stats(account['id'])
    g.data['auto_imports'] = get_account_auto_imports(account['id'])

    return make_template('account/account.html', 200)

@account.route('/account', methods=['POST'])
def post_account():
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))

    errors = False

    action = get_value(request.form, 'action')
    if action == 'change_password':
        current_password = get_value(request.form, 'current_password')
        new_password = get_value(request.form, 'password')
        confirm_new_password = get_value(request.form, 'confirm_password')

        if confirm_new_password != new_password:
            flash('New passwords do not match')
            errors = True

        if not check_password(account['username'], current_password):
            errors = True

        if get_value(current_app.config, 'ENABLE_PASSWORD_VALIDATOR', False) and is_password_compromised(new_password):
            flash('We\'ve detected that password was compromised in a data breach on another site. Please choose a different password.')
            errors = True

        if not errors:
            change_password(account['id'], new_password)
            flash('Password changed successfully')

    if action == 'change_display_name':
        display_name = get_value(request.form, 'display_name')
        if is_display_name_taken(display_name):
            flash('Display name already taken')
            errors = True

        if not errors:
            change_display_name(account['id'], display_name)

    return redirect(url_for('account.get_account'))

@account.route('/api/account/auto_imports', methods=['DELETE'])
def delete_auto_import():
    service = get_value(request.form, 'service')
    account = load_account()
    if account is None:
        return '', 401
    delete_sessions_for_service(service, account['id'])
    return '', 204
