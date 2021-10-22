import sys
sys.setrecursionlimit(100000)

import requests
import config
import json
import datetime
from urllib.parse import urljoin
from os.path import join
from bs4 import BeautifulSoup

from flask import current_app

from ...lib.artist import is_artist_dnp, get_artist_id_from_service_data, create_artist_entry, reattempt_failed_artist_metadata_imports, finalize_artist_import, get_artist, get_artist_display_name
from ...lib.post import remove_post_if_flagged_for_reimport, get_post_id_from_service_data, insert_post, is_post_import_finished, finalize_post_import, set_and_upload_post_thumbnail_if_needed, set_post_content, update_post, is_post_dnp, insert_extra_post_content, is_flagged_for_reimport, get_all_processed_sub_ids, mark_sub_id_processed, remove_content_with_sub_id, set_post_import_not_finished, insert_post_embed
from ...lib.account import mark_account_as_subscribed_to_artists, get_account_stats
from ...lib.file import insert_and_upload_post_file
from ...lib.auto_importer import decrease_session_retries_remaining
from ...utils.proxy import get_proxy
from ...utils.download import fetch_file_and_data, remove_temp_files
from ...utils.utils import get_import_id, date_to_utc, do_with_retries, replace_many, get_value, filter_urls, create_scrapper_session, get_multi_level_value, any_not_in
from ...utils.logger import log
from ...utils.import_lock import take_lock, release_lock

# In the future, if the timeline API proves itself to be unreliable, we should probably move to scanning fanclubs individually.
# https://fantia.jp/api/v1/me/fanclubs',

def enable_adult_mode(import_id, jar):
    scraper = create_scrapper_session(useCloudscraper = False).get(
        'https://fantia.jp/mypage/account/edit',
        cookies = jar,
        proxies = get_proxy()
    )
    scraper_data = scraper.text
    scraper.raise_for_status()
    soup = BeautifulSoup(scraper_data, 'html.parser')

    if soup.select_one('.edit_user input#user_rating') is None:
        log(import_id, 'Error while enabling adult mode')
        return (True, False)
        
    if soup.select_one('.edit_user input#user_rating').get('checked') is None:
        authenticity_token = soup.select_one('.edit_user input[name=authenticity_token]')['value']
        create_scrapper_session(useCloudscraper = False).post(
            'https://fantia.jp/mypage/users/update_rating',
            cookies = jar,
            proxies = get_proxy(),
            data = {
                'utf8': '✓',
                'authenticity_token': authenticity_token,
                'user[rating]': 'adult',
                'commit': '変更を保存'
            }
        ).raise_for_status()
        return (False, True)
    return (False, False)
    
def disable_adult_mode(import_id, jar):
    scraper = create_scrapper_session(useCloudscraper = False).get(
        'https://fantia.jp/mypage/account/edit',
        cookies = jar,
        proxies = get_proxy()
    )
    scraper_data = scraper.text
    scraper.raise_for_status()
    soup = BeautifulSoup(scraper_data, 'html.parser')
    authenticity_token = soup.select_one('.edit_user input[name=authenticity_token]')['value']
    create_scrapper_session(useCloudscraper = False).post(
        'https://fantia.jp/mypage/users/update_rating',
        cookies = jar,
        proxies = get_proxy(),
        data = {
            'utf8': '✓',
            'authenticity_token': authenticity_token,
            'user[rating]': 'adult',
            'commit': '変更を保存'
        }
    ).raise_for_status()

def import_fanclub(import_id, fanclub_id, account_id, jar):
    log(import_id, f'Importing fanclub {fanclub_id}')
    user_id = str(fanclub_id)
    artist_id = None
    
    for post_id in get_post_ids_for_fanclub(import_id, fanclub_id, jar):
        resource_id = None
        import_lock_id = None
        internal_post_id = None

        try:
            if is_post_dnp('fantia', user_id, post_id):
                log(import_id, f'Post {post_id} from artist {user_id} is in do not post list. Skipping.')
                continue

            if is_artist_dnp('fantia', user_id):
                log(import_id, f'Artist {user_id} is in do not post list. Skipping post {post_id}')
                continue

            import_lock_id = take_lock('fantia', user_id, post_id)
            if import_lock_id is None:
                log(import_id, f'Skipping post {post_id} from artist {user_id} because it is being imported by someone else right now')
                continue

            try:
                post_scraper = create_scrapper_session(useCloudscraper = False).get(
                    f'https://fantia.jp/api/v1/posts/{post_id}',
                    cookies = jar,
                    proxies = get_proxy()
                )
                post_json = post_scraper.json()
                post_scraper.raise_for_status()
            except requests.HTTPError as exc:
                log(import_id, f'Error contacting Fantia API for post {post_id}', 'exception')
                continue

            any_visible = False
            any_paid_visible = False
            visible_content_ids = []
            for content in get_multi_level_value(post_json, 'post', 'post_contents', default = []):
                content_id = get_value(content, 'id')
                visible_status = get_value(content, 'visible_status')
                plan_price = get_multi_level_value(content, 'plan', 'price', default = 0)
                if visible_status == 'visible':
                    any_visible = True
                    visible_content_ids.append(str(content_id))
                if visible_status == 'visible' and plan_price > 0:
                    any_paid_visible = True
            if not any_visible:
                log(import_id, f'No content from post {post_id} by artist {user_id} is visible. Skipping')
                continue
            if not any_paid_visible:
                log(import_id, f'Skipping post {post_id} from artist {user_id} because no paid content is visible', to_client = False)
                continue

            is_reimport = is_flagged_for_reimport('fantia', user_id, post_id)
            processed_content_ids = get_all_processed_sub_ids('fantia', user_id, post_id)
            if not any_not_in(visible_content_ids, processed_content_ids) and not is_reimport:
                log(import_id, f'Skipping post {post_id} from artist {user_id} because it was already imported')
                continue

            artist_id = get_artist_id_from_service_data('fantia', user_id)
            if artist_id is None:
                display_name = get_artist_display_name('fantia', user_id)
                artist_id = create_artist_entry('fantia', user_id, display_name)
            reattempt_failed_artist_metadata_imports('fantia', user_id, artist_id)

            post_data = {
                'service': 'fantia',
                'service_artist_id': user_id,
                'service_id': post_id,
                'artist_id': artist_id,
                'title': post_json['post']['title'],
                'content': post_json['post']['comment'] or '',
                'is_manual_upload': False,
                'added_at': datetime.datetime.utcnow(),
                'published_at': post_json['post']['posted_at'],
                'updated_at': None,
                'import_succeeded': False
            }


            if is_reimport:
                log(import_id, f'Post {post_id} from artist {user_id} was flagged for reimport. Reimporting')
                internal_post_id = get_post_id_from_service_data('fantia', user_id, post_id)
                update_post(post_data, internal_post_id)
                set_post_import_not_finished(internal_post_id, artist_id)
            else:
                log(import_id, f'Importing post {post_id} from artist {user_id}')
                internal_post_id = insert_post(post_data)

            resource_id = f'post{internal_post_id}'

            if get_multi_level_value(post_json, 'post', 'thumb') is not None:
                file_data = fetch_file_and_data(post_json['post']['thumb']['original'], cookies = jar, resource_id = resource_id)
                file_data['post_id'] = internal_post_id
                file_data['service'] = 'fantia'
                set_and_upload_post_thumbnail_if_needed(file_data)

            for content in get_multi_level_value(post_json, 'post', 'post_contents', default = []):
                sub_id = str(get_value(content, 'id'))

                if get_value(content, 'visible_status') != 'visible':
                    continue

                if is_reimport:
                    remove_content_with_sub_id(internal_post_id, sub_id)

                if get_value(content, 'category') == 'photo_gallery':
                    for photo in get_value(content, 'post_content_photos', []):
                        file_data = fetch_file_and_data(photo['url']['original'], cookies = jar, resource_id = resource_id)
                        file_data['path'] = f'files/fantia/{internal_post_id}/{file_data["name"]}'
                        file_data['post_id'] = internal_post_id
                        file_data['service'] = 'fantia'
                        file_data['comment'] = get_value(photo, 'comment')
                        file_data['sub_id'] = sub_id
                        set_and_upload_post_thumbnail_if_needed(file_data)
                        insert_and_upload_post_file(file_data)
                elif get_value(content, 'category') == 'file':
                    file_data = fetch_file_and_data(urljoin('https://fantia.jp/posts', content['download_uri']), cookies = jar, resource_id = resource_id)
                    file_data['name'] = get_value(content, 'filename') or file_data['name']
                    file_data['path'] = f'files/fantia/{internal_post_id}/{file_data["name"]}'
                    file_data['post_id'] = internal_post_id
                    file_data['service'] = 'fantia'
                    file_data['sub_id'] = sub_id

                    set_and_upload_post_thumbnail_if_needed(file_data)
                    insert_and_upload_post_file(file_data)
                elif get_value(content, 'category') == 'embed':
                    embed = {
                        'url': content['embed_url'],
                        'subject': '(embedded link)',
                        'description': '',
                        'sub_id': sub_id
                    }
                    insert_post_embed(internal_post_id, embed)
                elif get_value(content, 'category') == 'blog':
                    for op in get_value(json.loads(get_value(content, 'comment', '{}')), 'ops', []):
                        if get_multi_level_value(op, 'insert', 'fantiaImage'):
                            file_data = fetch_file_and_data(urljoin('https://fantia.jp/', op['insert']['fantiaImage']['original_url']), cookies = jar, resource_id = resource_id)
                            file_data['path'] = f'files/fantia/{internal_post_id}/{file_data["name"]}'
                            file_data['post_id'] = internal_post_id
                            file_data['service'] = 'fantia'
                            file_data['sub_id'] = sub_id
                            set_and_upload_post_thumbnail_if_needed(file_data)
                            insert_and_upload_post_file(file_data)
                elif get_value(content, 'category') == 'text':
                    comment = get_value(content, 'comment')
                    if comment is not None:
                        title = get_value(content, 'title')
                        insert_extra_post_content(internal_post_id, comment, title, sub_id)
                else:
                    log(import_id, f'Skipping content {content["id"]} from post {post_id}; unsupported type: {content["category"]}')
                    log(import_id, json.dumps(content), to_client = False)
            
                mark_sub_id_processed(internal_post_id, sub_id)
            finalize_post_import(internal_post_id, artist_id)

            log(import_id, f'Finished importing {post_id} for artist {user_id}', to_client = False)
        except Exception:
            log(import_id, f'Error importing post {post_id} from artist {user_id}', 'exception')
            continue
        finally:
            if import_lock_id is not None:
                release_lock(import_lock_id)
            if resource_id is not None:
                remove_temp_files(resource_id)

    if artist_id is not None:
        finalize_artist_import(artist_id)

def import_posts(import_id, key, account_id):
    jar = requests.cookies.RequestsCookieJar()
    jar.set('_session_id', key)
    
    (unauthorized, mode_switched) = enable_adult_mode(import_id, jar)
    if unauthorized:
        if account_id is not None:
            decrease_session_retries_remaining(key, 'fantia', account_id)
        log(import_id, 'Invalid key. No posts will be imported')
        return

    try:
        paid_fanclubs = get_paid_fanclubs(import_id, jar)
        artist_ids = []
        for fanclub_id in paid_fanclubs:
            import_fanclub(import_id, fanclub_id, account_id, jar)
            artist_ids.append(get_artist_id_from_service_data('fantia', fanclub_id))
    finally:
        if mode_switched:
            disable_adult_mode(import_id, jar)

    if account_id is not None:
        mark_account_as_subscribed_to_artists(account_id, artist_ids, 'fantia')
        get_account_stats(account_id, True)

    if len(paid_fanclubs) > 0:
        log(import_id, 'Finished scanning for posts')
    else:
        log(import_id, f'Finished scanning for posts. No posts detected')

def get_post_ids_for_fanclub(import_id, fanclub_id, jar):
    page_number = 1
    while True:
        list_scraper = create_scrapper_session(useCloudscraper = False).get(
            f'https://fantia.jp/fanclubs/{fanclub_id}/posts?page={page_number}',
            cookies = jar,
            proxies = get_proxy()
        )
        list_data = list_scraper.text
        list_scraper.raise_for_status()

        response_page = BeautifulSoup(list_data, 'html.parser')
        posts = response_page.select('div.post')

        post_count = 0
        for post in posts:
            link = post.select_one('a.link-block')['href']
            post_id = link.lstrip('/posts/')
            post_count += 1
            yield post_id

        if post_count == 0:
            return

        page_number += 1

def get_paid_fanclubs(import_id, jar):
    club_scraper = create_scrapper_session(useCloudscraper = False).get(
        'https://fantia.jp/mypage/users/plans?type=not_free',
        cookies = jar,
        proxies = get_proxy()
    )
    club_data = club_scraper.text
    club_scraper.raise_for_status()
    response_page = BeautifulSoup(club_data, 'html.parser')
    fanclub_links = response_page.select('div.mb-5-children > div:nth-of-type(1) a[href^="/fanclubs"]')

    clubs = set()
    for fanclub_link in fanclub_links:
        try:
            fanclub_id = fanclub_link['href'].lstrip('/fanclubs/')
            clubs.add(fanclub_id)
        except:
            log(import_id, f'Error importing club {fanclub_link}', 'exception')
            continue
    return clubs
