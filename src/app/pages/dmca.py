from flask import Blueprint, make_response, redirect, url_for

from ...utils.utils import make_template

dmca = Blueprint('dmca', __name__)

@dmca.route('/dmca')
def get_dmca():
    return make_template('dmca/dmca.html', 200)
