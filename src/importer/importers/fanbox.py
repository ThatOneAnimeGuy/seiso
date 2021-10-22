import sys
sys.path.append('./src/vendor/PixivUtil2')
sys.setrecursionlimit(100000)

import requests
import datetime
from gallery_dl import text
from bs4 import BeautifulSoup

from flask import current_app

from ...vendor.PixivUtil2.PixivModelFanbox import FanboxArtist, FanboxPost
from ...lib.artist import is_artist_dnp, get_artist_id_from_service_data, create_artist_entry, reattempt_failed_artist_metadata_imports, finalize_artist_import, get_artist
from ...lib.post import remove_post_if_flagged_for_reimport, get_post_id_from_service_data, insert_post, is_post_import_finished, finalize_post_import, set_and_upload_post_thumbnail_if_needed, set_post_content, update_post, is_post_dnp
from ...lib.account import mark_account_as_subscribed_to_artists, get_account_stats
from ...lib.file import insert_and_upload_post_file
from ...lib.auto_importer import decrease_session_retries_remaining
from ...utils.proxy import get_proxy
from ...utils.download import fetch_file_and_data, remove_temp_files
from ...utils.utils import get_import_id, date_to_utc, do_with_retries, replace_many, get_value, filter_urls, get_scraper_json, is_http_success
from ...utils.logger import log
from ...utils.import_lock import take_lock, release_lock

def import_posts(import_id, key, account_id, url = 'https://api.fanbox.cc/post.listSupporting?limit=50'):
    jar = requests.cookies.RequestsCookieJar()
    jar.set('FANBOXSESSID', key)

    import_feed(import_id, jar, account_id, url)

def import_feed(import_id, jar, account_id, url, artists_in_import = None):
    if artists_in_import is None:
        artists_in_import = set()

    try:
        (status, scraper_data) = get_scraper_json(url, jar, headers = {'origin': 'https://fanbox.cc'}, return_status = True)
        if not is_http_success(status):
            if account_id is not None:
                decrease_session_retries_remaining(jar.get('FANBOXSESSID'), 'fanbox', account_id)
            log(import_id, 'Invalid key. No posts will be imported')
            return
    except:
        log(import_id, f'Error when contacting Fanbox API ({url}). Stopping import.', 'exception')
        return

    if get_value(scraper_data, 'body') is not None:
        for post in scraper_data['body']['items']:
            resource_id = None
            import_lock_id = None
            internal_post_id = None
            try:
                user_id = str(post['user']['userId'])
                display_name = post['user']['name']
                user_name = post['creatorId']
                post_id = str(post['id'])

                if is_post_dnp('fanbox', user_id, post_id):
                    log(import_id, f'Post {post_id} from artist {user_id} is in do not post list. Skipping.')
                    continue

                if is_artist_dnp('fanbox', user_id):
                    log(import_id, f'Artist {user_id} is in do not post list. Skipping post {post_id}')
                    continue

                import_lock_id = take_lock('fanbox', user_id, post_id)
                if import_lock_id is None:
                    log(import_id, f'Skipping post {post_id} from artist {user_id} because it is being imported by someone else right now')
                    continue

                artist_id = get_artist_id_from_service_data('fanbox', user_id)
                if artist_id is None:
                    artist_id = create_artist_entry('fanbox', user_id, display_name, user_name)
                reattempt_failed_artist_metadata_imports('fanbox', user_id, artist_id)
                artists_in_import.add(artist_id)

                parsed_post = FanboxPost(post_id, None, post)
                if parsed_post.is_restricted:
                    log(import_id, f'Skipping post {post_id} from artist {user_id} because post is from higher subscription tier')
                    continue

                is_reimport = remove_post_if_flagged_for_reimport('fanbox', user_id, post_id)

                if is_post_import_finished('fanbox', user_id, post_id):
                    log(import_id, f'Skipping post {post_id} from artist {user_id} because it was already imported')
                    continue

                post_data = {
                    'service': 'fanbox',
                    'service_artist_id': user_id,
                    'service_id': post_id,
                    'artist_id': artist_id,
                    'title': post['title'],
                    'content': '',
                    'is_manual_upload': False,
                    'added_at': datetime.datetime.utcnow(),
                    'published_at': date_to_utc(parsed_post.worksDateDateTime),
                    'updated_at': date_to_utc(parsed_post.updatedDateDatetime),
                    'import_succeeded': False
                }

                if is_reimport:
                    log(import_id, f'Post {post_id} from artist {user_id} was flagged for reimport. Reimporting')
                    internal_post_id = get_post_id_from_service_data('fanbox', user_id, post_id)
                    update_post(post_data, internal_post_id)
                else:
                    log(import_id, f'Importing post {post_id} from artist {user_id}')
                    internal_post_id = insert_post(post_data)

                resource_id = f'post{internal_post_id}'

                if parsed_post.body_text is not None:
                    content, files = get_embedded_files(parsed_post.body_text, jar, resource_id)
                    if content.count('{{FILE_DATA_HERE}}') != len(files):
                        log(import_id, f'File count does not match number of replacements for content in post {post_id} from {user_id}: {content}. Files: {files}', 'warning', to_client = False)
                        log(import_id, f'Detected data inconsistency in post {post_id} from artist {artist_id}. Skipping')
                    else:
                        post_file_ids = []
                        for file in files:
                            file_data = file['data']
                            file_data['path'] = f'files/fanbox/{internal_post_id}/{file_data["name"]}'
                            file_data['post_id'] = internal_post_id
                            file_data['service'] = 'fanbox'
                            file_data['is_inline'] = True
                            file_data['inline_content'] = get_value(file, 'inline_content')

                            set_and_upload_post_thumbnail_if_needed(file_data)
                            post_file_id = insert_and_upload_post_file(file_data)
                            post_file_ids.append(f'{{{{post_file_{post_file_id}}}}}')

                        if len(files) > 0:
                            content = replace_many(content, '{{FILE_DATA_HERE}}', *post_file_ids)
                    set_post_content(internal_post_id, content)

                for url in filter_urls(parsed_post.embeddedFiles):
                    file_data = fetch_file_and_data(url, cookies = jar, headers = {'origin': 'https://fanbox.cc'}, resource_id = resource_id)
                    file_data['path'] = f'files/fanbox/{internal_post_id}/{file_data["name"]}'
                    file_data['post_id'] = internal_post_id
                    file_data['service'] = 'fanbox'

                    set_and_upload_post_thumbnail_if_needed(file_data)
                    insert_and_upload_post_file(file_data)

                finalize_post_import(internal_post_id, artist_id)

                log(import_id, f'Finished importing {post_id} for artist {user_id}', to_client = False)
            except Exception as e:
                log(import_id, f'Error importing post {post_id} from artist {user_id}', 'exception')
                continue
            finally:
                if import_lock_id is not None:
                    release_lock(import_lock_id)
                if resource_id is not None:
                    remove_temp_files(resource_id)

        next_url = scraper_data['body'].get('nextUrl')
        if next_url:
            del scraper_data # Memory usage optimization
            log(import_id, 'Processing next page')
            import_feed(import_id, jar, account_id, next_url, artists_in_import)
        else:
            for artist_id in artists_in_import:
                finalize_artist_import(artist_id)
            if account_id is not None:
                mark_account_as_subscribed_to_artists(account_id, artists_in_import, 'fanbox')
                get_account_stats(account_id, True)

            if len(artists_in_import) > 0:
                log(import_id, 'Finished scanning for posts')
            else:
                log(import_id, f'Finished scanning for posts. No posts detected')
    else:
        log(import_id, f'No posts found on Fanbox for this session id')

def get_embedded_files(content, jar, resource_id):
    files = []

    s = BeautifulSoup(content, features = 'html.parser')

    for anchor in s.findAll('a'):
        file = {}
        url = get_value(anchor, 'href')
        if url is None:
            continue

        try:
            file_data = fetch_file_and_data(url, cookies = jar, headers = {'origin': 'https://fanbox.cc'}, resource_id = resource_id)
            if file_data is None:
                continue
        except:
            continue

        file['url'] = url
        file['data'] = file_data
        if not anchor.find('img'):
            file['inline_content'] = str(anchor.contents[0])

        anchor.replaceWith('{{FILE_DATA_HERE}}')
        files.append(file)
    return str(s), files
