from datetime import datetime, timezone
from flask import request, g, current_app, make_response, render_template, current_app
import dateutil
import json
import re
import urllib
import random
import hashlib
import io
import os
import magic
import mimetypes
import time
import validators
import cloudscraper
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import src.utils.proxy as proxy

def allowed_file(mime, accepted):
    return any(x in mime for x in accepted)

def get_value(d, key, default = None):
    try:
        return d[key]
    except:
        return default

def get_multi_level_value(d, *keys, **kwargs):
    default = get_value(kwargs, 'default')

    depth = len(keys)
    for i in range(depth):
        key = keys[i]
        d = get_value(d, key)
        if d is None and i < depth:
            return default
    return d

def url_is_for_non_logged_file_extension(path):
    parts = path.split('/')
    if len(parts) == 0:
        return False

    blocked_extensions = ['js', 'css', 'ico', 'svg']
    for extension in blocked_extensions:
        if ('.' + extension) in parts[-1]:
            return True
    return False

def sort_dict_list_by(l, key, reverse = False):
    return sorted(l, key=lambda v: v[key], reverse=reverse)

def restrict_value(value, allowed, default = None):
    if value not in allowed:
        return default
    return value

def take(num, l):
    if len(l) <= num:
        return l
    return l[:num]

def offset(num, l):
    if len(l) <= num:
        return []
    return l[num:]

def limit_int(i, limit):
    if i > limit:
        return limit
    return i

def parse_int(string, default = 0):
    try:
        return int(string)
    except Exception:
        return default

def render_page_data():
    return json.dumps(g.page_data)

def get_import_id(data):
    salt = str(random.randrange(0, 100000))
    return take(8, hashlib.sha256((data + salt).encode('utf-8')).hexdigest())

def sha256(bytes):
    return hashlib.sha256(bytes).hexdigest()

def parse_date(string, default = None):
    if string is None:
        return default

    try:
        return dateutil.parser.parse(string)
    except (ValueError, OverflowError):
        return default

def get_config(name, default = None):
    return get_value(current_app.config, name, default)

def get_filename_from_cd(cd):
    if not cd:
        return None
    fname = re.findall(r"filename\*=([^;]+)", cd, flags=re.IGNORECASE)
    if len(fname) == 0:
        return None
    if not fname:
        fname = re.findall("filename=([^;]+)", cd, flags=re.IGNORECASE)
    if "utf-8''" in fname[0].lower():
        fname = re.sub("utf-8''", '', fname[0], flags=re.IGNORECASE)
        fname = urllib.parse.unquote(fname)
    else:
        fname = fname[0]
    return fname.strip().strip('"')

def slugify(text):
    if text is None:
        return ''

    non_url_safe = ['"', '#', '$', '%', '&', '+',
    ',', '/', ':', ';', '=', '?',
    '@', '[', '\\', ']', '^', '`',
    '{', '|', '}', '~', "'"]
    non_safe = [c for c in text if c in non_url_safe]
    if non_safe:
        for c in non_safe:
            text = text.replace(c, '')
    text = u'_'.join(text.split())
    return text

def filter_dict(d, func):
    ret = {}
    for key, value in d.items():
        if func(key, value):
            ret[key] = value
    return ret

def map_dict(d, func):
    ret = {}
    for key, value in d.items():
        (k, v) = func(key, value)
        ret[k] = v
    return ret

def get_columns_from_row_by_prefix(row, prefix):
    return map_dict(
        filter_dict(row, lambda key, _: key.startswith(prefix)),
        lambda key, value: (key.replace(f'{prefix}_', ''), value)
    )

def date_to_utc(date):
    if date is None:
        return None
    return date.astimezone(timezone.utc)

def is_mime_type_image(mime_type):
    mime_start = mime_type.split('/')[0]
    if mime_start == 'image':
        return True
    return False

def head(l):
    if l is None or len(l) == 0:
        return None
    return l[0]

def merge_dicts(d1, d2):
    return {**d1, **d2}

def make_template(template, status = 200, headers = {}):
    g.data['base'] = request.args.to_dict()
    g.data['base'] = merge_dicts(g.data['base'], request.view_args)
    if 'page' in g.data['base']:
        g.data['base'].pop('page')

    response = make_response(render_template(
        template,
        data = g.data,
    ), status)

    for key, value in headers.items():
        response.headers[key] = value
    return response

def get_request_ip():
    return request.headers.getlist("X-Forwarded-For")[0].rpartition(' ')[-1] if 'X-Forwarded-For' in request.headers else request.remote_addr

def get_file_metadata(file_path):
    with open(file_path, 'rb') as f:
        first_bytes = f.read(2048)
        mime_type = magic.from_buffer(first_bytes, mime = True)
        extension = mimetypes.guess_extension(mime_type, strict = False) or '.txt'
        if extension == '.jpe':
            extension = '.jpeg'

    return (mime_type, extension)

def cdn(path, bucket_name):
    cdns = get_config('S3_BUCKETS')
    cdn_scheme = get_config('CDN_BASE_URL_SCHEME')
    cdn_prefix = get_value(cdns, bucket_name)
    if cdn_prefix is not None:
        return os.path.join(cdn_scheme + '://' + cdn_prefix + '.' + get_config('CDN_BASE_URL'), path)
    return ''

def is_image_file(file):
    return is_mime_type_image(file['mime_type'])

def has_preview(file):
    return get_value(file, 'preview_path') is not None

def make_background_image(path, bucket_name):
    if path is not None:
        return f'background-image: url(\'{cdn(path, bucket_name)}\');'
    return ''

def pluralify_word(number, word):
    if word == 'has' and number != 1:
        return 'have'
    if number != 1:
        return word + 's'
    return word

def pluralify(number, word, include_number = True):
    if number > 1 or number == 0:
        word = word + 's'
    if not include_number:
        return word
    return f'{number} {word}'

def page_to_offset(page, limit = 25):
    return (page - 1) * limit

def count_to_pages(total_count, limit = 25):
    overflow = total_count % limit
    pages = int(total_count/limit)
    if overflow > 0:
        pages += 1
    return pages

def get_offset_from_url_query(limit = 25):
    page = parse_int(request.args.get('page'), 1)
    if page <= 0:
        page = 1
    return page_to_offset(page, limit)

def do_with_retries(func, attempts, *args, **kwargs):
    sleep_time = kwargs.get('sleep', 10)
    try:
        return func(*args)
    except:
        if attempts > 1:
            current_app.logger.error(f'Error calling {func.__name__}. Sleeping for {sleep_time}s before trying again. {attempts - 1} attempts remaining.')
            time.sleep(sleep_time)
            return do_with_retries(func, attempts - 1, *args, **kwargs)
        else:
            raise

def replace_many(string, search, *args):
    for arg in args:
        string = string.replace(search, arg, 1)
    return string

def limit_string(string, length):
    if len(string) <= length:
        return string
    return string[0:length]

def url_encode(d):
    return urllib.parse.urlencode(d)

def filter_urls(l):
    urls = []
    if type(l) is not list:
        return urls

    for e in l:
        e = str(e)
        if validators.url(e):
            urls.append(e)
    return urls

def create_scrapper_session(useCloudscraper = True, retries = 10, backoff_factor = 0.3, status_forcelist = (502, 503, 504, 423, 429)):
    session = None
    if useCloudscraper:
        session = cloudscraper.create_scraper()
    else:
        session = Session()

    retry = Retry(
        total = retries,
        read = retries,
        connect = retries,
        backoff_factor = backoff_factor,
        status_forcelist = status_forcelist,
    )
    adapter = HTTPAdapter(max_retries = retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def get_scraper_text(url, jar):
    return_status = kwargs.get('return_status', False)
    scraper = create_scrapper_session(useCloudscraper = False).get(
        url,
        cookies = jar,
        proxies = proxy.get_proxy()
    )
    if return_status:
        try:
            return (scraper.status_code, scraper.json())
        except:
            return (scraper.status_code, None)
    else:
        scraper_data = scraper.text
        scraper.raise_for_status()
        return scraper_data

def get_scraper_json(url, jar, **kwargs):
    return_status = kwargs.get('return_status', False)
    headers = kwargs.get('headers', dict())
    scraper = create_scrapper_session(useCloudscraper = False).get(
        url,
        cookies = jar,
        proxies = proxy.get_proxy(),
        headers = headers
    )
    if return_status:
        try:
            return (scraper.status_code, scraper.json())
        except:
            return (scraper.status_code, None)
    else:
        scraper_data = scraper.json()
        scraper.raise_for_status()
        return scraper_data

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for byte_block in iter(lambda: f.read(262144), b''):
            h.update(byte_block)
        return h.hexdigest()

def any_not_in(vals, to_check_against):
    for val in vals:
        if val not in to_check_against:
            return True
    return False

def service_to_display_name(service):
    if service == 'patreon':
        return 'Patreon'
    elif service == 'fanbox':
        return 'Pixiv Fanbox'
    elif service == 'fantia':
        return 'Fantia'

def is_http_success(status_code):
    return status_code >= 200 and status_code < 300
