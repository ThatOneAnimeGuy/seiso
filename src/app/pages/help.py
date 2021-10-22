from flask import Blueprint, render_template, make_response

from ...utils.utils import make_template

help_app = Blueprint('help_app', __name__)

@help_app.route('/')
def help():
    return make_template('help_list.html', 200)

@help_app.route('/posts')
def posts():
    return make_template('help_posts.html', 200)

@help_app.route('/about')
def about():
    return make_template('about.html', 200)

@help_app.route('/bans')
def bans():
    return make_template('bans.html', 200)

@help_app.route('/license')
def license():
    return make_template('license.html', 200)

@help_app.route('/rules')
def rules():
    return make_template('rules.html', 200)