from flask import Blueprint, redirect, url_for, g

from ...lib.artist import get_random_artist_ids, get_artist
from ...lib.post import get_random_posts_keys, get_post

import random as rand

random = Blueprint('random', __name__)

@random.route('/posts/random')
def get_random_post():
    post = find_random_post()
    if post is None:
        return redirect('back')

    return redirect(url_for('post.get', service = post['service'], artist_id = post['artist_id'], post_id = post['id']))

@random.route('/artists/random')
def get_random_artist():
    artist = find_random_artist()
    if artist is None:
        return redirect('back')

    return redirect(url_for('artists.get', service = artist['service'], artist_id = artist['id']))

def find_random_post():
    post_keys = get_random_posts_keys(1000)
    if len(post_keys) == 0:
        return None
    return get_post(rand.choice(post_keys), True)

def find_random_artist():
    artists = get_random_artist_ids(1000)
    if len(artists) == 0:
        return None
    return get_artist(rand.choice(artists))
