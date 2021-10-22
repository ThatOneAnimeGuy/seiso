from flask import Blueprint, redirect, url_for, g, request

from ...utils.utils import get_file_metadata, get_config, get_request_ip, restrict_value, get_value, make_template, get_offset_from_url_query , count_to_pages
from ...utils.object_storage import upload_file
from ...lib.request import get_requests_for_list, get_requests_search_results, get_request, ip_has_voted_for_request_already, insert_request, insert_request_vote, get_total_request_count

requests = Blueprint('requests', __name__)

@requests.route('/requests')
def get_list():
    offset = get_offset_from_url_query()
    query = get_value(request.args, 'query')
    status = get_value(request.args, 'status')
    service = get_value(request.args, 'service')
    sort_by = restrict_value(get_value(request.args, 'sort_by'), ['votes', 'created_at', 'price'], 'votes')
    sort_direction = restrict_value(get_value(request.args, 'sort_by'), ['asc', 'desc'], 'desc')
    max_price = get_value(request.args, 'max_price')
    total_count = get_total_request_count()

    is_search = (query, status or service or sort_by or sort_direction or max_price) is not None

    if not is_search:
        g.data['results'] = get_requests_for_list(offset)
    else:
        g.data['results'] = get_requests_search_results(status, service, sort_by, sort_direction, max_price)

    g.data['max_pages'] = count_to_pages(total_count)

    return make_template('requests_list.html', 200)

@requests.route('/requests/<request_id>/vote_up', methods=['POST'])
def vote_up(request_id):
    user_ip = get_request_ip()
    request = get_request(request_id)

    if request is None:
        return redirect(url_for('requests.list'))

    if ip_has_voted_for_request_already(request_id, user_ip):
        return '', 400
    else:
        insert_request_vote(request_id, user_ip)
        return '', 200

@requests.route('/requests/new')
def request_form():
    return make_template('requests_new.html', 200)

@requests.route('/requests/new', methods=['POST'])
def request_submit():
    if not request.form.get('service_id'):
        flash('You must provide an id')
        return redirect(url_for('requests.request_form'))

    image_filename = None
    try:
        if 'image' in request.files:
            image_bytes = request.files['image'].read()
            image_size = len(image_bytes)

            if image_size > get_config('MAX_REQUEST_IMAGE_SIZE'):
                flash('Image is too large (must me 1MB or less)')
                return make_template('requests_new.html', 200)

            (mime_type, extension) = get_file_metadata(image_bytes)
            image_filename = take(32, sha256(image_bytes)) + extension
            upload_file(f'requests/{image_filename}', image_bytes, mime_type)
    except Exception:
        current_app.logger.exception('Error uploading request image')
        flash('Error uploading image. Try again.')
        return make_template('requests_new.html', 200)

    service = get_value(request.form, 'service')
    service_id = get_value(request.form, 'service_id')
    price = get_value(request.form, 'price')

    success = insert_request(service, service_id, price, image_filename)
    if not success:
        flash('There is already a request with this Service and Service ID')

    return redirect(url_for('requests.list'))
