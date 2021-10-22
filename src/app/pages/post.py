from flask import Blueprint, request, make_response, render_template, redirect, url_for, g, flash

import datetime
import re

from ...internals.database.database import get_cursor
from ...lib.post import get_post, is_post_flagged, get_next_post_id, get_previous_post_id, get_recent_posts_for_listing, get_total_post_count, mark_post_for_reimport, delete_post, add_post_to_dnp_list
from ...lib.artist import get_artist
from ...lib.favorites import is_post_favorited
from ...lib.account import load_account, is_admin
from ...utils.utils import make_template, cdn, count_to_pages, parse_int, page_to_offset, get_offset_from_url_query, has_preview, get_value

post = Blueprint('post', __name__)

@post.route('/post/<service>/<artist_id>/<post_id>/prev')
def get_prev(service, artist_id, post_id):
    previous_post_id = get_previous_post_id(post_id, artist_id)

    if previous_post_id is None:
        return redirect(request.headers.get('Referer') if request.headers.get('Referer') else '/')
    else:
        prev_post = get_post(previous_post_id)
        return redirect(url_for('post.get', service = prev_post['service'], artist_id = prev_post['artist_id'], post_id = previous_post_id))

@post.route('/post/<service>/<artist_id>/<post_id>/next')
def get_next(service, artist_id, post_id):
    next_post_id = get_next_post_id(post_id, artist_id)
    
    if next_post_id is None:
        return redirect(request.headers.get('Referer') if request.headers.get('Referer') else '/')
    else:
        next_post = get_post(next_post_id)
        return redirect(url_for('post.get', service = next_post['service'], artist_id = next_post['artist_id'], post_id = next_post_id))

@post.route('/post/<service>/<artist_id>/<post_id>')
def get(service, artist_id, post_id):
    post = get_post(post_id)
    if post is None:
        response = redirect(url_for('artists.get', service = service, artist_id = artist_id))
        return response

    favorited = False
    account = load_account()
    if account is not None:
        favorited = is_post_favorited(account['id'], post_id)
        g.data['is_admin'] = is_admin(account)

    artist = get_artist(artist_id)

    post['content'] = inject_inline_images(post['content'], post['files'])
    post['content'] = inject_newlines(post['content'], post['service'])

    g.data['artist'] = artist
    g.data['flagged'] = is_post_flagged(post_id)
    g.data['favorited'] = favorited
    g.data['post'] = post
    
    return make_template('post/post.html', 200)

@post.route('/post/recent')
def get_recent():
    offset = get_offset_from_url_query()
    g.data['results'] = get_recent_posts_for_listing(offset)
    g.data['max_pages'] = count_to_pages(get_total_post_count())

    return make_template('posts.html', 200)

@post.route('/post/flag/<post_id>', methods=['POST'])
def post_flag(post_id):
    mark_post_for_reimport(post_id)
    return '', 200

@post.route('/post/delete/<post_id>', methods=['POST'])
def delete(post_id):
    account = load_account()
    if account is None:
        return '', 403

    if not is_admin(account):
        return '', 403

    post = get_post(post_id, True)
    artist = get_artist(post['artist_id'])
    add_post_to_dnp_list(post_id)
    delete_post(post_id)
    flash(f'Post deleted')
    return redirect(url_for('artists.get', service = artist['service'], artist_id = artist['id']))

# @post.route('/posts/upload', methods=['GET'])
# def get_upload_post():
#     return make_template('upload.html', 200)

# @post.route('/posts/upload', methods=['POST'])
# def post_upload_post():
#     return "Temporarily disabled due to spam.", 200
    # resumable_dict = {
    #     'resumableIdentifier': request.form.get('resumableIdentifier'),
    #     'resumableFilename': request.form.get('resumableFilename'),
    #     'resumableTotalSize': request.form.get('resumableTotalSize'),
    #     'resumableTotalChunks': request.form.get('resumableTotalChunks'),
    #     'resumableChunkNumber': request.form.get('resumableChunkNumber')
    # }

    # if int(request.form.get('resumableTotalSize')) > int(getenv('UPLOAD_LIMIT')):
    #     return "File too large.", 415

    # makedirs(join(getenv('DB_ROOT'), 'uploads'), exist_ok=True)
    # makedirs(join(getenv('DB_ROOT'), 'uploads', 'temp'), exist_ok=True)

    # resumable = UploaderFlask(
    #     resumable_dict,
    #     join(getenv('DB_ROOT'), 'uploads'),
    #     join(getenv('DB_ROOT'), 'uploads', 'temp'),
    #     request.files['file']
    # )

    # resumable.upload_chunk()

    # if resumable.check_status() is True:
    #     resumable.assemble_chunks()
    #     try:
    #         resumable.cleanup()
    #     except:
    #         pass

    #     post_model = {
    #         'id': ''.join(random.choice(string.ascii_letters) for x in range(8)),
    #         '"user"': request.form.get('user'),
    #         'service': request.form.get('service'),
    #         'title': request.form.get('title'),
    #         'content': request.form.get('content') or "",
    #         'embed': {},
    #         'shared_file': True,
    #         'added': datetime.now(),
    #         'published': datetime.now(),
    #         'edited': None,
    #         'file': {
    #             "name": request.form.get('resumableFilename'),
    #             "path": f"/uploads/{request.form.get('resumableFilename')}"
    #         },
    #         'attachments': []
    #     }

    #     post_model['embed'] = json.dumps(post_model['embed'])
    #     post_model['file'] = json.dumps(post_model['file'])
        
    #     columns = post_model.keys()
    #     data = ['%s'] * len(post_model.values())
    #     data[-1] = '%s::jsonb[]' # attachments
    #     query = "INSERT INTO posts ({fields}) VALUES ({values})".format(
    #         fields = ','.join(columns),
    #         values = ','.join(data)
    #     )
    #     cursor = get_cursor()
    #     cursor.execute(query, list(post_model.values()))
        
    #     return jsonify({
    #         "fileUploadStatus": True,
    #         "resumableIdentifier": resumable.repo.file_id
    #     })

    # return jsonify({
    #     "chunkUploadStatus": True,
    #     "resumableIdentifier": resumable.repo.file_id
    # })

def inject_inline_images(content, files):
    for file in files:
        if file['is_inline']:
            inline_content = get_value(file, 'inline_content')
            injected_content = '';
            if has_preview(file):
                injected_content = f'<a href="{cdn(file["path"], file["bucket_name"])}"><img src="{cdn(file["preview_path"], file["bucket_name"])}"/></a>'
            elif inline_content is not None:
                injected_content = f'<a href="{cdn(file["path"], file["bucket_name"])}">{inline_content}</a>'
            else:
                injected_content = f'<a href="{cdn(file["path"], file["bucket_name"])}">Click here to download embedded file</a>'
            content = content.replace(f'{{{{post_file_{file["id"]}}}}}', injected_content)
    return content

def inject_newlines(content, service):
    if service == 'fantia' or service == 'fanbox':
        content = content.replace('\n', '<br/>')
    return content
