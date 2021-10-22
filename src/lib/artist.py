from flask import current_app

from bs4 import BeautifulSoup
import dateutil
import datetime
import cloudscraper
import requests

from ..internals.cache.redis import get_redis, serialize, deserialize, delete_keys
from ..internals.database.database import get_cursor, get_conn
from ..utils.utils import get_value, get_columns_from_row_by_prefix, take, offset, get_multi_level_value, get_config, create_scrapper_session
from ..utils.proxy import get_proxy
from ..utils.object_storage import upload_file_bytes, delete_file
from ..utils.download import fetch_file_and_data, remove_temp_files
from ..utils.image_processing import make_banner, make_icon

def get_recently_indexed_artists(offset, limit):
    redis = get_redis()
    key = f'recently_indexed_artists:{offset}:{limit}'
    artists = redis.get(key)
    if artists is None:
        with get_cursor() as cursor:
            query = """
                SELECT
                    a.id artist_id,
                    a.service artist_service,
                    a.service_id artist_service_id,
                    a.display_name artist_display_name,
                    a.created_at artist_created_at,
                    a.last_indexed artist_last_indexed,
                    a.last_post_imported_at last_post_imported_at,
                    ab.path banner_path,
                    ab.retries_remaining banner_retries_remaining,
                    ab.id banner_id,
                    ab.updated_at banner_updated_at,
                    ab.bucket_name banner_bucket_name,
                    ai.path icon_path,
                    ai.retries_remaining icon_retries_remaining,
                    ai.id icon_id,
                    ai.updated_at icon_updated_at,
                    ai.bucket_name icon_bucket_name
                FROM artist a
                LEFT JOIN artist_banner ab ON ab.artist_id = a.id
                LEFT JOIN artist_icon ai ON ai.artist_id = a.id
                WHERE last_post_imported_at IS NOT NULL
                ORDER BY last_post_imported_at DESC
                OFFSET %s
                LIMIT %s
            """
            cursor.execute(query, (offset, limit,))
            rows = cursor.fetchall()

            artists = []
            for row in rows:
                artist = get_columns_from_row_by_prefix(row, 'artist')
                artist['banner'] = get_columns_from_row_by_prefix(row, 'banner')
                artist['icon'] = get_columns_from_row_by_prefix(row, 'icon')
                artists.append(artist)
        redis.set(key, serialize(artists))
    else:
        artists = deserialize(artists)
    return artists

def get_artist_count(reload = False):
    redis = get_redis()
    key = 'artist_count'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT count(*) as count FROM artist WHERE last_post_imported_at IS NOT NULL'
            cursor.execute(query)
            count = cursor.fetchone()['count']
        redis.set(key, count)
    else:
        count = int(count)
    return count

def is_artist_dnp(service, service_id):
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM do_not_post_request WHERE service_id = %s AND service = %s", (service_id, service,))
        return cursor.fetchone() is not None

def get_top_artists_by_faves(offset, count, reload = False):
    redis = get_redis()
    key = f'top_artists:{offset}:{count}'
    artists = redis.get(key)
    if artists is None or reload:
        with get_cursor() as cursor:
            query = """
                SELECT
                    a.id artist_id,
                    a.service artist_service,
                    a.service_id artist_service_id,
                    a.display_name artist_display_name,
                    a.created_at artist_created_at,
                    a.last_indexed artist_last_indexed,
                    a.last_post_imported_at last_post_imported_at,
                    ab.path banner_path,
                    ab.retries_remaining banner_retries_remaining,
                    ab.id banner_id,
                    ab.updated_at banner_updated_at,
                    ab.bucket_name banner_bucket_name,
                    ai.path icon_path,
                    ai.retries_remaining icon_retries_remaining,
                    ai.id icon_id,
                    ai.updated_at icon_updated_at,
                    ai.bucket_name icon_bucket_name
                FROM artist a
                LEFT JOIN artist_banner ab ON ab.artist_id = a.id
                LEFT JOIN artist_icon ai ON ai.artist_id = a.id
                INNER JOIN account_artist_favorite aaf
                    ON a.id = aaf.artist_id
                GROUP BY a.id, ab.id, ai.id
                ORDER BY count(*) DESC
                OFFSET %s
                LIMIT %s
            """
            cursor.execute(query, (offset, count,))
            rows = cursor.fetchall()

            artists = []
            for row in rows:
                artist = get_columns_from_row_by_prefix(row, 'artist')
                artist['banner'] = get_columns_from_row_by_prefix(row, 'banner')
                artist['icon'] = get_columns_from_row_by_prefix(row, 'icon')
                artists.append(artist)

        redis.set(key, serialize(artists), ex = 3600)
        get_count_of_artists_faved(True)
    else:
        artists = deserialize(artists)
    return artists

def get_count_of_artists_faved(reload = False):
    redis = get_redis()
    key = 'artists_faved_count'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = """
                SELECT count(distinct(a.id))
                FROM artist a
                INNER JOIN account_artist_favorite aaf
                    ON a.id = aaf.artist_id
            """
            cursor.execute(query)
            count = cursor.fetchone()['count']
        redis.set(key, count, ex = 3600)
    else:
        count = int(count)
    return count

def get_top_artists_by_recent_faves(offset, count, reload = False):
    redis = get_redis()
    key = f'top_artists_recently_v2:{offset}:{count}'
    artists = redis.get(key)
    if artists is None or reload:
        with get_cursor() as cursor:
            query = """
                SELECT
                    a.id artist_id,
                    a.service artist_service,
                    a.service_id artist_service_id,
                    a.display_name artist_display_name,
                    a.created_at artist_created_at,
                    a.last_indexed artist_last_indexed,
                    a.last_post_imported_at last_post_imported_at,
                    ab.path banner_path,
                    ab.retries_remaining banner_retries_remaining,
                    ab.id banner_id,
                    ab.updated_at banner_updated_at,
                    ab.bucket_name banner_bucket_name,
                    ai.path icon_path,
                    ai.retries_remaining icon_retries_remaining,
                    ai.id icon_id,
                    ai.updated_at icon_updated_at,
                    ai.bucket_name icon_bucket_name
                FROM artist a
                LEFT JOIN artist_banner ab ON ab.artist_id = a.id
                LEFT JOIN artist_icon ai ON ai.artist_id = a.id
                INNER JOIN (
                    SELECT * FROM account_artist_favorite
                    ORDER BY id DESC LIMIT 1000
                ) aaf
                ON a.id = aaf.artist_id
                GROUP BY a.id, ab.id, ai.id
                ORDER BY count(*) DESC
                OFFSET %s
                LIMIT %s
            """
            cursor.execute(query, (offset, count,))
            rows = cursor.fetchall()

            artists = []
            for row in rows:
                artist = get_columns_from_row_by_prefix(row, 'artist')
                artist['banner'] = get_columns_from_row_by_prefix(row, 'banner')
                artist['icon'] = get_columns_from_row_by_prefix(row, 'icon')
                artists.append(artist)

        redis.set(key, serialize(artists), ex = 3600)
        get_count_of_artists_recently_faved(True)
    else:
        artists = deserialize(artists)
    return artists

def get_count_of_artists_recently_faved(reload = False):
    redis = get_redis()
    key = 'artists_recently_faved_count_v2'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = """
                SELECT count(distinct(a.id))
                FROM artist a
                INNER JOIN (
                    SELECT * FROM account_artist_favorite
                    ORDER BY id DESC LIMIT 1000
                ) aaf
                ON a.id = aaf.artist_id
            """
            cursor.execute(query)
            count = cursor.fetchone()['count']
        redis.set(key, count, ex = 3600)
    else:
        count = int(count)
    return count

def get_random_artist_ids(count, reload = False):
    redis = get_redis()
    key = f'random_artist_ids:{count}'
    artist_ids = redis.get(key)
    if artist_ids is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT id FROM artist ORDER BY random() LIMIT %s'
            cursor.execute(query, (count,))
            artist_ids = [row['id'] for row in cursor.fetchall()]
        redis.set(key, serialize(artist_ids), ex = 900)
    else:
        artist_ids = deserialize(artist_ids)
    return artist_ids

def get_artist(artist_id, reload = False):
    redis = get_redis()
    key = f'artist_v2:{artist_id}'
    artist = redis.get(key)
    if artist is None or reload:
        with get_cursor() as cursor:
            query = """
                SELECT
                    a.id artist_id,
                    a.service artist_service,
                    a.service_id artist_service_id,
                    a.display_name artist_display_name,
                    a.created_at artist_created_at,
                    a.last_indexed artist_last_indexed,
                    a.last_post_imported_at last_post_imported_at,
                    ab.path banner_path,
                    ab.retries_remaining banner_retries_remaining,
                    ab.id banner_id,
                    ab.updated_at banner_updated_at,
                    ab.bucket_name banner_bucket_name,
                    ai.path icon_path,
                    ai.retries_remaining icon_retries_remaining,
                    ai.id icon_id,
                    ai.updated_at icon_updated_at,
                    ai.bucket_name icon_bucket_name
                FROM artist a
                LEFT JOIN artist_banner ab ON ab.artist_id = a.id
                LEFT JOIN artist_icon ai ON ai.artist_id = a.id
                WHERE a.id = %s
            """
            cursor.execute(query, (artist_id,))
            row = cursor.fetchone()

        if row is not None:
            artist = get_columns_from_row_by_prefix(row, 'artist')
            artist['banner'] = get_columns_from_row_by_prefix(row, 'banner')
            artist['icon'] = get_columns_from_row_by_prefix(row, 'icon')
        else:
            artist = None

        redis.set(key, serialize(artist))
    else:
        artist = deserialize(artist)
    return artist

def get_artist_search_results(q, service, o, limit):
    with get_cursor() as cursor:
        query = """
            SELECT id artist_id
            FROM artist
            WHERE
                (%(raw_query)s = '' OR display_name ILIKE %(like_query)s OR username ILIKE %(like_query)s OR service_id = %(raw_query)s)
                AND
                (%(service)s = '' OR service = %(service)s)
                AND last_post_imported_at IS NOT NULL
            ORDER BY last_post_imported_at DESC
        """
        like_query = f'%{q}%'
        cursor.execute(query, {'like_query': like_query, 'raw_query': q, 'service': service})
        rows = cursor.fetchall()
    artists = []
    for row in take(limit, offset(o, rows)):
        artists.append(get_artist(row['artist_id']))

    return (artists, len(rows))

def get_artist_post_count(artist_id, reload = False):
    redis = get_redis()
    key = f'artist_post_count:{artist_id}'
    count = redis.get(key)
    if count is None or reload:
        with get_cursor() as cursor:
            query = 'SELECT count(*) as count FROM post WHERE artist_id = %s AND is_import_finished = true'
            cursor.execute(query, (artist_id,))
            count = cursor.fetchone()['count']
        redis.set(key, str(count))
    else:
        count = int(count)
    return count

def get_artist_id_from_service_data(service, service_id):
    with get_cursor() as cursor:
        cursor.execute('SELECT id FROM artist WHERE service = %s AND service_id = %s', (service, service_id,))
        data = cursor.fetchall()
        if len(data) > 0:
            return get_value(data[0], 'id')
    return None

def get_artist_display_name(service, service_id):
    try:
        if service == 'patreon':
            user = create_scrapper_session().get('https://api.patreon.com/user/' + service_id, proxies=get_proxy()).json()
            return get_multi_level_value(user, 'included', 0, 'attributes', 'name') or get_multi_level_value(user, 'data', 'attributes', 'vanity') or get_multi_level_value('data', 'attributes', 'full_name')
        elif service == 'fanbox':
            user = requests.get('https://api.fanbox.cc/creator.get?userId=' + service_id, proxies=get_proxy(), headers={"origin":"https://fanbox.cc"}).json()
            return user["body"]["creatorId"],
        elif service == 'gumroad':
            resp = requests.get('https://gumroad.com/' + service_id, proxies=get_proxy()).text
            soup = BeautifulSoup(resp, 'html.parser')
            return soup.find('h2', class_='creator-profile-card__name js-creator-name').string.replace("\n", "")
        elif service == 'subscribestar':
            resp = requests.get('https://subscribestar.adult/' + service_id, proxies=get_proxy()).text
            soup = BeautifulSoup(resp, 'html.parser')
            return  soup.find('div', class_='profile_main_info-name').string
        elif service == 'dlsite':
            resp = requests.get('https://www.dlsite.com/eng/circle/profile/=/maker_id/' +service_id, proxies=get_proxy()).text
            soup = BeautifulSoup(resp, 'html.parser')
            return soup.find('strong', class_='prof_maker_name').string
        elif service == 'fantia':
            resp = requests.get(f'https://fantia.jp/api/v1/fanclubs/{service_id}', proxies = get_proxy()).json()
            return get_multi_level_value(resp, 'fanclub', 'name') or get_multi_level_value(resp, 'fanclub', 'fanclub_name_or_creator_name')
    except:
        current_app.logger.exception(f'Error getting data for artist {service_id} from {service}')
        return f'{service} artist {service_id}'

def get_and_save_artist_banner(service, service_id, internal_artist_id):
    banner_data = None
    try:
        url = None
        if service == 'patreon':
            scraper = create_scrapper_session().get('https://api.patreon.com/user/' + service_id, proxies = get_proxy())
            data = scraper.json()
            scraper.raise_for_status()
            if data.get('included') and data['included'][0]['attributes'].get('cover_photo_url'):
                url = data['included'][0]['attributes']['cover_photo_url']
        elif service == 'fanbox':
            scraper = requests.get('https://api.fanbox.cc/creator.get?userId=' + service_id, headers={"origin":"https://fanbox.cc"}, proxies=get_proxy())
            data = scraper.json()
            scraper.raise_for_status()
            if data['body']['coverImageUrl']:
                url = data['body']['coverImageUrl']
        elif service == 'subscribestar':
            scraper = requests.get('https://subscribestar.adult/' + service_id, proxies=get_proxy())
            data = scraper.text
            scraper.raise_for_status()
            soup = BeautifulSoup(data, 'html.parser')
            if soup.find('img', class_='profile_main_info-cover'):
                url = soup.find('img', class_='profile_main_info-cover')['src']
        elif service == 'fantia':
            resp = requests.get(f'https://fantia.jp/api/v1/fanclubs/{service_id}', proxies = get_proxy()).json()
            url = get_multi_level_value(resp, 'fanclub', 'cover', 'original')

        if url is not None:
            resource_id = f'artist{internal_artist_id}'
            banner_data = fetch_file_and_data(url, resource_id = resource_id)
            if banner_data is None:
                decrement_banner_retries(internal_artist_id)
                return

            banner_path = f'banners/{internal_artist_id}.jpg'
            (reduced_banner_bytes, mime_type) = make_banner(banner_data['local_path'])
            upload_file_bytes(banner_path, reduced_banner_bytes, mime_type)
            set_artist_banner_path(internal_artist_id, banner_path)
            remove_temp_files(resource_id)
        else:
            decrement_banner_retries(internal_artist_id)
    except:
        current_app.logger.exception(f'Exception importing banner for {internal_artist_id} ({service})')
        decrement_banner_retries(internal_artist_id)

def decrement_banner_retries(artist_id):
    with get_cursor() as cursor:
        cursor.execute("INSERT INTO artist_banner (artist_id, retries_remaining) VALUES (%s, 4) ON CONFLICT (artist_id) DO UPDATE SET retries_remaining = artist_banner.retries_remaining - 1", (artist_id,))
    get_artist(artist_id, True)

def set_artist_banner_path(artist_id, path):
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO artist_banner (artist_id, path, bucket_name, updated_at)
            VALUES (%s, %s, %s, timezone('utc', now()))
            ON CONFLICT (artist_id) DO
                UPDATE SET path = excluded.path, bucket_name = excluded.bucket_name, updated_at = timezone('utc', now())
        """, (artist_id, path, get_config('S3_BUCKET_NAME')))
    get_artist(artist_id, True)

def get_and_save_artist_icon(service, service_id, internal_artist_id):
    icon_data = None
    try:
        url = None
        if service == 'patreon':
            data = create_scrapper_session().get('https://api.patreon.com/user/' + service_id, proxies = get_proxy()).json()
            url = data['included'][0]['attributes']['avatar_photo_url'] if data.get('included') else data['data']['attributes']['image_url']
        elif service == 'fanbox':
            scraper = requests.get('https://api.fanbox.cc/creator.get?userId=' + service_id, headers={"origin":"https://fanbox.cc"}, proxies = get_proxy())
            data = scraper.json()
            scraper.raise_for_status()
            if data['body']['user']['iconUrl']:
                url = data['body']['user']['iconUrl']
        elif service == 'subscribestar':
            scraper = requests.get('https://subscribestar.adult/' + service_id, proxies = get_proxy())
            data = scraper.text
            scraper.raise_for_status()
            soup = BeautifulSoup(data, 'html.parser')
            url = soup.find('div', class_='profile_main_info-userpic').contents[0]['src']
        elif service == 'gumroad':
            scraper = requests.get('https://gumroad.com/' + service_id, proxies = get_proxy())
            data = scraper.text
            scraper.raise_for_status()
            soup = BeautifulSoup(data, 'html.parser')
            url = re.findall(r'(?:http\:|https\:)?\/\/.*\.(?:png|jpe?g|gif)', soup.find('div', class_='profile-picture js-profile-picture')['style'], re.IGNORECASE)[0]
        elif service == 'fantia':
            resp = requests.get(f'https://fantia.jp/api/v1/fanclubs/{service_id}', proxies = get_proxy()).json()
            url = get_multi_level_value(resp, 'fanclub', 'icon', 'original')

        if url is not None:
            resource_id = f'artist{internal_artist_id}'
            icon_data = fetch_file_and_data(url, resource_id = resource_id)
            if icon_data is None:
                decrement_icon_retries(internal_artist_id)
                return

            icon_path = f'icons/{internal_artist_id}.jpg'
            (reduced_icon_bytes, mime_type) = make_icon(icon_data['local_path'])
            upload_file_bytes(icon_path, reduced_icon_bytes, mime_type)
            set_artist_icon_path(internal_artist_id, icon_path)
            remove_temp_files(resource_id)
        else:
            decrement_icon_retries(internal_artist_id)
    except:
        current_app.logger.exception(f'Exception when downloading icons for artist {internal_artist_id} ({service})')
        decrement_icon_retries(internal_artist_id)

def decrement_icon_retries(artist_id):
    with get_cursor() as cursor:
        cursor.execute("INSERT INTO artist_icon (artist_id, retries_remaining) VALUES (%s, 4) ON CONFLICT (artist_id) DO UPDATE SET retries_remaining = artist_icon.retries_remaining - 1", (artist_id,))
    get_artist(artist_id, True)

def set_artist_icon_path(artist_id, path):
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO artist_icon (artist_id, path, bucket_name, updated_at)
            VALUES (%s, %s, %s, timezone('utc', now()))
            ON CONFLICT (artist_id) DO
                UPDATE SET path = excluded.path, bucket_name = excluded.bucket_name, updated_at = timezone('utc', now())
        """, (artist_id, path, get_config('S3_BUCKET_NAME')))
    get_artist(artist_id, True)

def reattempt_failed_artist_metadata_imports(service, service_id, internal_artist_id):
    artist = get_artist(internal_artist_id)

    banner_retries = artist['banner']['retries_remaining']
    if artist['banner']['path'] is None and (banner_retries is None or banner_retries > 0):
        get_and_save_artist_banner(service, service_id, internal_artist_id)

    icon_retries = artist['icon']['retries_remaining']
    if artist['icon']['path'] is None and (icon_retries is None or icon_retries > 0):
        get_and_save_artist_icon(service, service_id, internal_artist_id)

def create_artist_entry(service, service_id, display_name = None, user_name = None):
    if display_name is None:
        display_name = get_artist_display_name(service, service_id) or 'Unknown'

    with get_cursor() as cursor:
        query = "INSERT INTO artist (service, service_id, display_name, username) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id"
        cursor.execute(query, (service, service_id, display_name, user_name,))
        result = cursor.fetchone()

    if result is None:
        return get_artist_id_from_service_data(service, service_id)
    artist_id = result['id']

    get_and_save_artist_icon(service, service_id, artist_id)
    get_and_save_artist_banner(service, service_id, artist_id)

    get_artist(artist_id, True)
    return artist_id

def finalize_artist_import(artist_id):
    with get_cursor() as cursor:
        cursor.execute("UPDATE artist SET last_indexed = timezone('utc', now()) WHERE id = %s", (artist_id,))
    get_artist_count(True)
    get_artist(artist_id, True)
    delete_keys('recently_indexed_artists:*')

def delete_artist(artist_id):
    current_app.logger.debug(f'Deleting artist {artist_id}')
    try:
        files = []
        with get_cursor() as cursor:
            query = """
                SELECT preview_path path, pf.bucket_name bucket_name FROM post_file pf INNER JOIN post p ON pf.post_id = p.id WHERE p.artist_id = %(artist_id)s
                UNION ALL
                SELECT path, pf.bucket_name bucket_name FROM post_file pf INNER JOIN post p ON pf.post_id = p.id WHERE p.artist_id = %(artist_id)s
                UNION ALL
                SELECT thumbnail_path path, bucket_name FROM post WHERE artist_id = %(artist_id)s
                UNION ALL
                SELECT path, bucket_name FROM artist_banner WHERE artist_id = %(artist_id)s
                UNION ALL
                SELECT path, bucket_name FROM artist_icon WHERE artist_id = %(artist_id)s
            """
            cursor.execute(query, {'artist_id': artist_id})
            rows = cursor.fetchall()

        for row in rows:
            if row['path'] is not None:
                delete_file(row['path'], row['bucket_name'])

        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM processed_sub_id WHERE post_id IN (SELECT id FROM post WHERE artist_id = %s)', (artist_id,))
            cursor.execute('DELETE FROM account_post_favorite WHERE post_id IN (SELECT id FROM post WHERE artist_id = %s)', (artist_id,))
            cursor.execute('DELETE FROM post_file pf WHERE post_id IN (SELECT id FROM post WHERE artist_id = %s)', (artist_id,))
            cursor.execute('DELETE FROM post_embed WHERE post_id IN (SELECT id FROM post WHERE artist_id = %s)', (artist_id,))
            cursor.execute('DELETE FROM extra_post_content WHERE post_id IN (SELECT id FROM post WHERE artist_id = %s)', (artist_id,))
            cursor.execute('DELETE FROM post WHERE artist_id = %s', (artist_id,))
            cursor.execute('DELETE FROM artist_banner WHERE artist_id = %s', (artist_id,))
            cursor.execute('DELETE FROM artist_icon WHERE artist_id = %s', (artist_id,))
            cursor.execute('DELETE FROM account_artist_favorite WHERE artist_id = %s', (artist_id,))
            cursor.execute('DELETE FROM account_artist_subscription WHERE artist_id = %s', (artist_id,))
            cursor.execute('DELETE FROM artist WHERE id = %s', (artist_id,))
            conn.commit()
    except Exception:
        current_app.logger.exception(f'Error deleting artist {artist_id}')
    current_app.logger.debug(f'Finished deleting artist {artist_id}')
    get_artist(artist_id, True)
    get_artist_count(True)
    delete_keys('top_artists:*')
    delete_keys('top_artists_recently:*')
    get_count_of_artists_faved(True)
    get_count_of_artists_recently_faved(True)

def add_artist_to_dnp_list(artist_id):
    artist = get_artist(artist_id)
    with get_cursor() as cursor:
        query = 'INSERT INTO do_not_post_request (service, service_id) VALUES (%s, %s) ON CONFLICT DO NOTHING'
        cursor.execute(query, (artist['service'], artist['service_id'],))

def set_artist_last_post_imported_at_now(artist_id):
    with get_cursor() as cursor:
        cursor.execute("UPDATE artist SET last_post_imported_at = timezone('utc', now()) WHERE id = %s", (artist_id,))
