import sys
sys.setrecursionlimit(100000)

import datetime
import dateutil
import requests
from os.path import join
import uuid

from gallery_dl import text

from flask import current_app

from ...lib.artist import is_artist_dnp, get_artist_id_from_service_data, create_artist_entry, reattempt_failed_artist_metadata_imports, finalize_artist_import, get_artist, get_artist_display_name
from ...lib.post import remove_post_if_flagged_for_reimport, get_post_id_from_service_data, insert_post, is_post_import_finished, finalize_post_import, set_and_upload_post_thumbnail_if_needed, insert_post_embed, set_post_content, update_post, is_post_dnp
from ...lib.account import mark_account_as_subscribed_to_artists
from ...lib.file import insert_and_upload_post_file
from ...lib.auto_importer import decrease_session_retries_remaining
from ...utils.proxy import get_proxy
from ...utils.download import fetch_file_and_data, remove_temp_files
from ...utils.utils import date_to_utc, parse_date, head, get_value, do_with_retries, limit_string, slugify, get_multi_level_value, get_scraper_json, is_http_success
from ...utils.logger import log
from ...utils.import_lock import take_lock, release_lock

image_tag_before = '<img data-media-id="'
image_tag_after = '>'

def import_posts(import_id, key, account_id):
    jar = requests.cookies.RequestsCookieJar()
    jar.set('session_id', key)

    artists_in_import = set()
    campaign_ids = get_campaign_ids(jar, import_id)
    if campaign_ids is None:
        if account_id is not None:
            decrease_session_retries_remaining(key, 'patreon', account_id)
        log(import_id, 'Invalid key. No posts will be imported')
        return

    current_app.logger.debug(f'Account {account_id} has campaigns {campaign_ids}')
    if len(campaign_ids) > 0:
        for campaign_id in campaign_ids:
            log(import_id, f'Importing pledge {campaign_id}')
            import_campaign_page(posts_url + str(campaign_id), jar, import_id, artists_in_import)

        if account_id is not None:
            mark_account_as_subscribed_to_artists(account_id, artists_in_import, 'patreon')
        log(import_id, 'Finished scanning for posts')
    else:
        log(import_id, 'No active subscriptions. No posts will be imported')

def import_campaign_page(url, jar, import_id, artists_in_import):
    try:
        scraper_data = get_scraper_json(url, jar)
    except Exception:
        log(import_id, 'Error connecting to Patreon. Skipping pledge', 'exception')
        return set()

    for post in get_value(scraper_data, 'data', []):
        internal_post_id = None
        resource_id = None
        import_lock_id = None
        try:
            user_id = str(post['relationships']['user']['data']['id'])
            post_id = str(post['id'])

            if is_post_dnp('patreon', user_id, post_id):
                    log(import_id, f'Post {post_id} from artist {user_id} is in do not post list. Skipping.')
                    continue

            if is_artist_dnp('patreon', user_id):
                log(import_id, f'Artist {user_id} is in do not post list. Skipping post {post_id}', to_client = True)
                continue

            import_lock_id = take_lock('patreon', user_id, post_id)
            if import_lock_id is None:
                log(import_id, f'Skipping post {post_id} from artist {user_id} because it is being imported by someone else right now')
                continue

            can_view = get_multi_level_value(post, 'attributes', 'current_user_can_view')
            if can_view is not None and not can_view:
                log(import_id, f'Skipping {post_id} from artist {user_id} because post is from higher subscription tier')
                continue

            artist_id = get_artist_id_from_service_data('patreon', user_id)
            if artist_id is None:
                user_name = get_user_name_from_data(scraper_data, user_id)
                display_name = get_artist_display_name('patreon', user_id)
                artist_id = create_artist_entry('patreon', user_id, display_name, user_name)
            reattempt_failed_artist_metadata_imports('patreon', user_id, artist_id)
            artists_in_import.add(artist_id)

            is_reimport = remove_post_if_flagged_for_reimport('patreon', user_id, post_id)

            if is_post_import_finished('patreon', user_id, post_id):
                log(import_id, f'Skipping post {post_id} from artist {user_id} because it was already imported')
                continue

            post_data = {
                'service': 'patreon',
                'service_artist_id': user_id,
                'service_id': post_id,
                'artist_id': artist_id,
                'title': post['attributes']['title'] or '',
                'content': '',
                'is_manual_upload': False,
                'added_at': datetime.datetime.utcnow(),
                'published_at': date_to_utc(parse_date(post['attributes']['published_at'])),
                'updated_at': date_to_utc(parse_date(post['attributes']['edited_at'])),
                'import_succeeded': False
            }


            if is_reimport:
                log(import_id, f'Post {post_id} from artist {user_id} was flagged for reimport. Reimporting')
                internal_post_id = get_post_id_from_service_data('patreon', user_id, post_id)
                update_post(post_data, internal_post_id)
            else:
                log(import_id, f'Importing post {post_id} from artist {user_id}')
                internal_post_id = insert_post(post_data)

            resource_id = f'post{internal_post_id}'

            if get_multi_level_value(post, 'attributes', 'content') is not None:
                post_content = post['attributes']['content']
                for image in get_embedded_images(post_content):
                    download_url = text.extract(image, 'src="', '"')[0]

                    file_data = fetch_file_and_data(download_url, resource_id = resource_id)
                    file_data['path'] = f'files/patreon/{internal_post_id}/{file_data["name"]}'
                    file_data['post_id'] = internal_post_id
                    file_data['service'] = 'patreon'
                    file_data['is_inline'] = True

                    set_and_upload_post_thumbnail_if_needed(file_data)
                    post_file_id = insert_and_upload_post_file(file_data)

                    post_content = post_content.replace(image_tag_before + image + image_tag_after, f"{{{{post_file_{post_file_id}}}}}")
                set_post_content(internal_post_id, post_content)

            if get_multi_level_value(post, 'attributes', 'embed') is not None:
                embed = {
                    'subject': post['attributes']['embed']['subject'],
                    'description': post['attributes']['embed']['description'],
                    'url': post['attributes']['embed']['url']
                }
                insert_post_embed(internal_post_id, embed)

            if get_multi_level_value(post, 'attributes', 'post_file') is not None:
                file_data = fetch_file_and_data(post['attributes']['post_file']['url'], resource_id = resource_id)
                file_data['path'] = f'files/patreon/{internal_post_id}/{file_data["name"]}'
                file_data['post_id'] = internal_post_id
                file_data['service'] = 'patreon'

                set_and_upload_post_thumbnail_if_needed(file_data)
                insert_and_upload_post_file(file_data)

            for attachment in get_multi_level_value(post, 'relationships', 'attachments', 'data', default = []):
                file_data = fetch_file_and_data(f'https://www.patreon.com/file?h={post_id}&i={attachment["id"]}', cookies = jar, resource_id = resource_id)
                file_data['path'] = f'files/patreon/{internal_post_id}/{file_data["name"]}'
                file_data['post_id'] = internal_post_id
                file_data['service'] = 'patreon'

                set_and_upload_post_thumbnail_if_needed(file_data)
                insert_and_upload_post_file(file_data)                

            if get_multi_level_value(post, 'relationships', 'images', 'data') is not None:
                for image in post['relationships']['images']['data']:
                    for media in list(filter(lambda included: included['id'] == image['id'], scraper_data['included'])):
                        if media['attributes']['state'] != 'ready':
                            continue
                        file_data = fetch_file_and_data(media['attributes']['download_url'], resource_id = resource_id)
                        file_data['name'] = limit_string(slugify(media['attributes']['file_name'] or str(uuid.uuid4())), 255)
                        file_data['path'] = f'files/patreon/{internal_post_id}/{file_data["name"]}'
                        file_data['post_id'] = internal_post_id
                        file_data['service'] = 'patreon'

                        set_and_upload_post_thumbnail_if_needed(file_data)
                        insert_and_upload_post_file(file_data)

            if get_multi_level_value(post, 'relationships', 'audio', 'data') is not None:
                for media in list(filter(lambda included: included['id'] == post['relationships']['audio']['data']['id'], scraper_data['included'])):
                    if media['attributes']['state'] != 'ready':
                        continue

                    file_data = fetch_file_and_data(media['attributes']['download_url'], resource_id = resource_id)
                    file_data['name'] = limit_string(slugify(media['attributes']['file_name'] or str(uuid.uuid4())), 255)
                    file_data['path'] = f'files/patreon/{internal_post_id}/{file_data["name"]}'
                    file_data['post_id'] = internal_post_id
                    file_data['service'] = 'patreon'

                    set_and_upload_post_thumbnail_if_needed(file_data)
                    insert_and_upload_post_file(file_data)

            finalize_post_import(internal_post_id, artist_id)

            log(import_id, f'Finished importing {post_id} from artist {user_id}', to_client = False)
        except Exception:
            log(import_id, f'Error while importing {post_id} from artist {user_id}', 'exception')
            continue
        finally:
            if import_lock_id is not None:
                release_lock(import_lock_id)
            if resource_id is not None:
                remove_temp_files(resource_id)

    next_url = get_multi_level_value(scraper_data, 'links', 'next')
    if next_url is not None:
        del scraper_data # Memory usage optimization
        log(import_id, 'Processing next page')
        import_campaign_page(next_url, jar, import_id, artists_in_import)
    else:
        for artist_id in artists_in_import:
            finalize_artist_import(artist_id)

def get_active_campaign_ids(jar, import_id):
    try:
        (status, scraper_data) = get_scraper_json(campaign_list_url, jar, return_status = True)
        if not is_http_success(status):
            return (True, set())
    except requests.HTTPError as e:
        log(import_id, f'Error connecting to Patreon API', 'exception')
        return (False, set())
    except Exception:
        log(import_id, 'Error connecting to cloudscraper. Please try again', 'exception')
        return (False, set())

    campaign_ids = set()
    for pledge in scraper_data['data']:
        try:
             campaign_id = pledge['relationships']['campaign']['data']['id']
             campaign_ids.add(campaign_id)
        except Exception as e:
            log(import_id, f'Error fetching pledge data; skipping pledge {pledge["id"]}', 'exception')
            continue

    return (False, campaign_ids)

# Retrieve ids of campaigns for which a pledge has been cancelled
# but they've been paid for in this or previous month
def get_cancelled_campaign_ids(jar, import_id):
    today_date = datetime.datetime.today()
    bill_data = []
    try:
        (status, scraper_data) = get_scraper_json(bills_url + str(today_date.year), jar, return_status = True)
        if not is_http_success(status):
            return (True, set())

        bill_data.extend(scraper_data['data'])

        # Get data for previous year as well if today's date is less or equal to Jan 7th
        if should_get_previous_year_data(today_date):
            (status, scraper_data) = get_scraper_json(bills_url + str(today_date.year - 1), jar, return_status = True)
            if not is_http_success(status):
                return (True, set())

            if 'data' in scraper_data and len(scraper_data['data']) > 0:
                bill_data.extend(scraper_data['data'])
    except requests.HTTPError as e:
        log(import_id, f'Error connecting to Patreon API', 'exception')
        return (False, set())
    except Exception:
        log(import_id, 'Error connecting to cloudscraper. Please try again', 'exception')
        return (False, set())

    bills = []
    for bill in bill_data:
        try:
            if bill['attributes']['status'] != 'successful':
                continue
            due_date = dateutil.parser.parse(bill['attributes']['due_date'])

            if is_bill_relevant(due_date, today_date):
                bills.append(bill)
        except Exception as e:
            log(import_id, 'Error while parsing billing data; skipping', 'exception')
            continue

    campaign_ids = set()
    if len(bills) > 0:
        for bill in bills:
            try:
                campaign_id = bill['relationships']['campaign']['data']['id']
                if not campaign_id in campaign_ids:
                    campaign_ids.add(campaign_id)
            except Exception as e:
                log(import_id, f'Error while retrieving a cancelled pledge', 'exception')
                continue

    return (False, campaign_ids)

def get_campaign_ids(jar, import_id):
    (unauthorized, campaign_ids) = get_active_campaign_ids(jar, import_id)
    if not unauthorized:
        (unauthorized, cancelled_campaign_ids) = get_cancelled_campaign_ids(jar, import_id)
        if not unauthorized:
            campaign_ids.update(cancelled_campaign_ids)
            return campaign_ids
    return None

def should_get_previous_year_data(today_date):
    return today_date.month == 1 and today_date.day <= 7

def is_bill_relevant(due_date, today_date):
    # We check all bills for the current month as well as bills from the previous month
    # for the first 7 days of the current month because posts are still available
    # for some time after cancelling membership
    return due_date.month == today_date.month or ((due_date.month == today_date.month - 1 or (due_date.month == 12 and today_date.month == 1)) and today_date.day <= 7)

def get_user_name_from_data(data, service_id):
    user_data = head(list(filter(lambda x: get_value(x, 'type') == 'user' and get_value(x, 'id') == int(service_id), data['included'])))
    return get_value(user_data, 'full_name')

def get_embedded_images(content):
    return text.extract_iter(content, image_tag_before, image_tag_after)

posts_url = 'https://www.patreon.com/api/posts' + '?include=' + ','.join([
    'user',
    'attachments',
    'campaign,poll.choices',
    'poll.current_user_responses.user',
    'poll.current_user_responses.choice',
    'poll.current_user_responses.poll',
    'access_rules.tier.null',
    'images.null',
    'audio.null'
]) + '&fields[post]=' + ','.join([
    'change_visibility_at',
    'comment_count',
    'content',
    'current_user_can_delete',
    'current_user_can_view',
    'current_user_has_liked',
    'embed',
    'image',
    'is_paid',
    'like_count',
    'min_cents_pledged_to_view',
    'post_file',
    'post_metadata',
    'published_at',
    'patron_count',
    'patreon_url',
    'post_type',
    'pledge_url',
    'thumbnail_url',
    'teaser_text',
    'title',
    'upgrade_url',
    'url',
    'was_posted_by_campaign_owner',
    'edited_at'
]) + '&fields[user]=' + ','.join([
    'image_url',
    'full_name',
    'url'
]) + '&fields[campaign]='+ ','.join([
    'show_audio_post_download_links',
    'avatar_photo_url',
    'earnings_visibility',
    'is_nsfw',
    'is_monthly',
    'name',
    'url'
]) + '&fields[access_rule]=' + ','.join([
    'access_rule_type',
    'amount_cents'
]) + '&fields[media]='+ ','.join([
    'id',
    'image_urls',
    'download_url',
    'metadata',
    'file_name',
    'state'
]) + '&sort=-published_at' \
+ '&filter[is_draft]=false' \
+ '&filter[contains_exclusive_posts]=true' \
+ '&json-api-use-default-includes=false&json-api-version=1.0' \
+ '&filter[campaign_id]=' #url should always end with this

campaign_list_url = 'https://www.patreon.com/api/pledges' + '?include=' + ','.join([
    'address',
    'campaign',
    'reward.items',
    'most_recent_pledge_charge_txn',
    'reward.items.reward_item_configuration',
    'reward.items.merch_custom_variants',
    'reward.items.merch_custom_variants.item',
    'reward.items.merch_custom_variants.merch_product_variant'
]) + '&fields[address]=' + ','.join([
    'id',
    'addressee',
    'line_1',
    'line_2',
    'city',
    'state',
    'postal_code',
    'country',
    'phone_number'
]) + '&fields[campaign]=' + ','.join([
    'avatar_photo_url',
    'cover_photo_url',
    'is_monthly',
    'is_non_profit',
    'name',
    'pay_per_name',
    'pledge_url',
    'published_at',
    'url'
]) + '&fields[user]=' + ','.join([
    'thumb_url',
    'url',
    'full_name'
]) + '&fields[pledge]=' + ','.join([
    'amount_cents',
    'currency',
    'pledge_cap_cents',
    'cadence',
    'created_at',
    'has_shipping_address',
    'is_paused',
    'status'
]) + '&fields[reward]=' + ','.join([
    'description',
    'requires_shipping',
    'unpublished_at'
]) + '&fields[reward-item]=' + ','.join([
    'id',
    'title',
    'description',
    'requires_shipping',
    'item_type',
    'is_published',
    'is_ended',
    'ended_at',
    'reward_item_configuration'
]) + '&fields[merch-custom-variant]=' + ','.join([
    'id',
    'item_id'
]) + '&fields[merch-product-variant]=' + ','.join([
    'id',
    'color',
    'size_code'
]) + '&fields[txn]=' + ','.join([
    'succeeded_at',
    'failed_at'
]) + '&json-api-use-default-includes=false&json-api-version=1.0'

bills_url = 'https://www.patreon.com/api/bills' + '?timezone=UTC' + '&include=' + ','.join([
    'post.campaign.null',
    'campaign.null',
    'card.null'
]) + '&fields[campaign]=' + ','.join([
    'avatar_photo_url',
    'currency',
    'cover_photo_url',
    'is_monthly',
    'is_non_profit',
    'is_nsfw',
    'name',
    'pay_per_name',
    'pledge_url',
    'url'
]) + '&fields[post]=' + ','.join([
    'title',
    'is_automated_monthly_charge',
    'published_at',
    'thumbnail',
    'url',
    'pledge_url'
]) + '&fields[bill]=' + ','.join([
    'status',
    'amount_cents',
    'created_at',
    'due_date',
    'vat_charge_amount_cents',
    'vat_country',
    'monthly_payment_basis',
    'patron_fee_cents',
    'is_non_profit',
    'bill_type',
    'currency',
    'cadence',
    'taxable_amount_cents'
]) + '&fields[patronage_purchase]=' + ','.join([
    'amount_cents',
    'currency',
    'created_at',
    'due_date',
    'vat_charge_amount_cents',
    'vat_country',
    'status',
    'cadence',
    'taxable_amount_cents'
]) + '&fields[card]=' + ','.join([ #we fetch the same fields as the patreon site itself to not trigger any possible protections. User card data is actually not saved or accessed.
    'number',
    'expiration_date',
    'card_type',
    'merchant_name',
    'needs_sfw_auth',
    'needs_nsfw_auth'
]) + '&json-api-use-default-includes=false&json-api-version=1.0&filter[due_date_year]='
