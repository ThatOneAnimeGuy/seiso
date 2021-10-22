from flask import Blueprint, request, make_response, render_template, session, redirect, url_for, g, flash

import re

from ...utils.utils import make_template, count_to_pages, get_offset_from_url_query, get_value
from ...internals.database.database import get_cursor
from ...lib.artist import get_artist, get_artist_post_count, get_top_artists_by_faves, get_count_of_artists_faved, get_top_artists_by_recent_faves, get_count_of_artists_recently_faved, get_artist_search_results, get_recently_indexed_artists, get_artist_count, delete_artist, add_artist_to_dnp_list
from ...lib.post import get_artist_posts_for_listing, is_post_flagged, get_artist_post_search_results
from ...lib.favorites import is_artist_favorited
from ...lib.account import load_account, is_admin
from ...utils.flask_thread import FlaskThread

artists = Blueprint('artists', __name__)

@artists.route('/artists', methods=['GET', 'POST'])
def get_list():
    query = request.args.get('query')
    service = request.args.get('service')
    offset = get_offset_from_url_query()

    if query is None and service is None:
        query = ''
        service = ''

    if query is not None:
        query = query.strip()

    (results, total_count) = get_artist_search_results(query, service, offset, 25)
    g.data['display'] = 'search results'
    g.data['results'] = results
    g.data['max_pages'] = count_to_pages(total_count)

    return make_template('artist_list_search.html', 200)

@artists.route('/artists/popular')
def get_popular():
    offset = get_offset_from_url_query()

    g.data['display'] = 'most popular artists'
    g.data['results'] = get_top_artists_by_faves(offset, 25)
    g.data['max_pages'] = count_to_pages(get_count_of_artists_faved())

    return make_template('artist_list_search.html', 200)

@artists.route('/artists/trending')
def get_trending():
    offset = get_offset_from_url_query()

    g.data['display'] = 'trending artists'
    g.data['results'] = get_top_artists_by_recent_faves(offset, 25)
    g.data['max_pages'] = count_to_pages(get_count_of_artists_recently_faved())

    return make_template('artist_list_search.html', 200)

@artists.route('/artists/recent')
def get_recent():
    offset = get_offset_from_url_query()

    g.data['display'] = 'recently added artists'
    g.data['results'] = get_recently_indexed_artists(offset, 25)
    g.data['max_pages'] = count_to_pages(get_artist_count())

    return make_template('artist_list_search.html', 200)

@artists.route('/artists/<service>/<artist_id>')
def get(service, artist_id):
    offset = get_offset_from_url_query()
    query = request.args.get('query')

    artist = get_artist(artist_id)
    if artist is None:
        return redirect(url_for('artists.get_list'))

    is_favorited = False
    account = load_account()
    if account is not None:
        is_favorited = is_artist_favorited(account['id'], artist_id)
        g.data['is_admin'] = is_admin(account)

    if query is not None:
        query = query.strip()

    (posts, total_count) = ([], 0)
    if query is None:
        (posts, total_count) = get_artist_post_page(artist_id, offset)
    else:
        (posts, total_count) = get_artist_post_search_results(query, artist_id, offset)

    g.data['results'] = posts
    g.data['artist'] = artist
    g.data['max_pages'] = count_to_pages(total_count)
    g.data['artist']['is_favorited'] = is_favorited
    g.data['artist']['display_data'] = make_artist_display_data(artist)

    return make_template('artist/artist.html', 200)

@artists.route('/artists/delete/<artist_id>', methods=['POST'])
def delete(artist_id):
    account = load_account()
    if account is None:
        return '', 403

    if not is_admin(account):
        return '', 403

    add_artist_to_dnp_list(artist_id)
    FlaskThread(target=delete_artist, args=(artist_id,)).start()
    flash(f'Starting deletion of artist {artist_id}. If the artist has a lot of posts, it may take a while to delete them.')
    return redirect(url_for('artists.get_list'))

def get_artist_post_page(artist_id, offset):
    posts = get_artist_posts_for_listing(artist_id, offset, 'published desc')
    total_count = get_artist_post_count(artist_id)
    return (posts, total_count)

def make_artist_display_data(artist):
    data = {}
    if artist['service'] == 'patreon':
        data['service'] = 'Patreon'
        data['href'] = f'https://www.patreon.com/user?u={artist["service_id"]}'
    elif artist['service'] == 'fanbox':
        data['service'] = 'Fanbox'
        data['href'] = f'https://www.pixiv.net/fanbox/creator/{artist["service_id"]}'
    elif artist['service'] == 'gumroad':
        data['service'] = 'Gumroad'
        data['href'] = f'https://gumroad.com/{artist["service_id"]}'
    elif artist['service'] == 'subscribestar':
        data['service'] = 'SubscribeStar'
        data['href'] = f'https://subscribestar.adult/{artist["service_id"]}'
    elif artist['service'] == 'fantia':
        data['service'] = 'Fantia'
        data['href'] = f'https://fantia.jp/fanclubs/{artist["service_id"]}'
    return data
