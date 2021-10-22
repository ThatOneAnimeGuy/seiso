from flask import Blueprint, make_response, redirect, url_for

from ...utils.utils import make_template

root = Blueprint('root', __name__)

@root.route('/')
def get_home():
    return redirect(url_for('artists.get_popular'), 301)

@root.route('/robots.txt')
def get_robots():
    robots = "User-agent: *\nDisallow: /\n"
    response = make_response(robots, 200)
    response.mimetype = 'text/plain'
    return response
