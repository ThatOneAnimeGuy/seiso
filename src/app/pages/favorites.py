from flask import Blueprint, request, make_response, render_template, session, redirect, flash, url_for, current_app, g

from ...utils.utils import get_value, restrict_value, sort_dict_list_by, take, offset, parse_int, make_template, page_to_offset, count_to_pages, get_offset_from_url_query
from ...lib.account import load_account
from ...lib.favorites import get_favorite_artists, get_favorite_posts, add_favorite_post, add_favorite_artist, remove_favorite_post, remove_favorite_artist, get_posts_by_favorited_artists, get_favorite_post_count, get_favorite_artist_count, get_count_of_posts_by_favorite_artists
from ...lib.security import is_password_compromised

favorites = Blueprint('favorites', __name__)

@favorites.route('/favorites/posts', methods=['GET'])
def get_posts():
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))

    offset = get_offset_from_url_query()
    sort_direction = restrict_value(get_value(request.args, 'sort_direction'), ['asc', 'desc'], 'desc')
    sort_field = restrict_value(get_value(request.args, 'sort'), ['id', 'published_at'], 'id')
    favorites = get_favorite_posts(account['id'], offset, sort_field, sort_direction)

    g.data['sort_field'] = sort_field
    g.data['sort_direction'] = sort_direction
    g.data['results'] = favorites
    g.data['max_pages'] = count_to_pages(get_favorite_post_count(account['id']))

    return make_template('favorites/posts.html', 200)

@favorites.route('/favorites/artists', methods=['GET'])
def get_artists():
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))

    offset = get_offset_from_url_query()
    sort_direction = restrict_value(get_value(request.args, 'sort_direction'), ['asc', 'desc'], 'desc')
    sort_field = restrict_value(get_value(request.args, 'sort'), ['id', 'last_indexed'], 'last_indexed')
    favorites = get_favorite_artists(account['id'], offset, sort_field, sort_direction)

    g.data['sort_field'] = sort_field
    g.data['sort_direction'] = sort_direction
    g.data['results'] = favorites
    g.data['max_pages'] = count_to_pages(get_favorite_artist_count(account['id']))

    return make_template('favorites/artists.html', 200)

@favorites.route('/favorites/artists/posts', methods=['GET'])
def get_favorite_artist_posts():
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))

    offset = get_offset_from_url_query()
    g.data['results'] = get_posts_by_favorited_artists(account['id'], offset)
    g.data['max_pages'] = count_to_pages(get_count_of_posts_by_favorite_artists(account['id']))

    return make_template('posts.html', 200)

@favorites.route('/favorites/post/<post_id>', methods=['POST'])
def post_favorite_post(post_id):
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))
    add_favorite_post(account['id'], post_id)
    return '', 200

@favorites.route('/favorites/artist/<artist_id>', methods=['POST'])
def post_favorite_artist(artist_id):
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))
    add_favorite_artist(account['id'], artist_id)
    return '', 200

@favorites.route('/favorites/post/<post_id>', methods=['DELETE'])
def delete_favorite_post(post_id):
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))
    remove_favorite_post(account['id'], post_id)
    return '', 200

@favorites.route('/favorites/artist/<artist_id>', methods=['DELETE'])
def delete_favorite_artist(artist_id):
    account = load_account()
    if account is None:
        return redirect(url_for('account.get_login'))
    remove_favorite_artist(account['id'], artist_id)
    return '', 200
