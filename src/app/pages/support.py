from flask import Blueprint, request, make_response, render_template

from ...utils.utils import make_template

support = Blueprint('support', __name__)

@support.route('/support')
def get_support():
    return make_template('support.html', 200)
