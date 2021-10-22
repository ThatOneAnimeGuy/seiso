from ..internals.database.database import get_cursor
from ..utils.utils import get_value, take
from ..internals.cache.redis import get_redis, serialize, deserialize
from ..lib.account import get_account_display_name, get_all_account_ids_with_imports

def get_leaderboard_display_data():
    redis = get_redis()
    key = 'top_25_account_scores_v3'
    account_display_list = redis.get(key)
    if account_display_list is None:
        account_list = get_top_25_accounts()
        account_display_list = []
        for (account_id, score) in account_list:
            account_display_list.append(make_account_display_data(account_id, score))
        redis.set(key, serialize(account_display_list), ex = 3600 * 2)
    else:
        account_display_list = deserialize(account_display_list)
    return account_display_list

def make_account_display_data(account_id, score):
    return {
        'account_id': account_id,
        'display_name': get_account_display_name(account_id),
        'score': "{:,}".format(score)
    }

def get_top_25_accounts():
    max_fave_count = get_max_fave_count()
    account_ids = get_all_account_ids_with_imports()

    scores = {}
    for account_id in account_ids:
        scores[account_id] = calculate_import_score(account_id, max_fave_count)

    return take(25, sorted(scores.items(), key = lambda item: item[1], reverse = True))

def get_max_fave_count():
    with get_cursor() as cursor:
        query = 'SELECT count(*) count FROM account_artist_favorite GROUP BY artist_id ORDER BY count(*) DESC LIMIT 1'
        cursor.execute(query)
        result = get_value(cursor.fetchone(), 'count')
        if result is None:
            return 1
        return result

def calculate_import_score(account_id, max_fave_count):
    score = 0.0
    with get_cursor() as cursor:
        query = """
            SELECT
                p.artist_id artist_id,
                count(p.id) post_count,
                (select count(*) from account_artist_favorite where artist_id = p.artist_id) fave_count
            FROM account_artist_subscription aas
            INNER JOIN post p ON aas.artist_id = p.artist_id
            WHERE
                p.added_at <= aas.last_imported_at
                AND
                aas.account_id = %s
            GROUP BY p.artist_id
        """
        cursor.execute(query, (account_id,))
        rows = cursor.fetchall()
        for row in rows:
            score += calculate_score_from_artist(row['artist_id'], row['post_count'], row['fave_count'], max_fave_count)

    return int(score)

def calculate_score_from_artist(artist_id, post_count, fave_count, max_fave_count):
    multiplier = fave_count/max_fave_count
    base_score = post_count
    score = base_score * multiplier
    return score
