from flask import Blueprint, g

from ...lib.leaderboard import get_leaderboard_display_data, get_max_fave_count, calculate_import_score, make_account_display_data
from ...lib.account import load_account
from ...utils.utils import make_template

leaderboard = Blueprint('leaderboard', __name__)

@leaderboard.route('/leaderboard')
def get_leaderboard():
    accounts = get_leaderboard_display_data()
    accounts = populate_accounts_with_my_info_if_logged_in(accounts)
    g.data['accounts'] = accounts
    return make_template('leaderboard/leaderboard.html', 200)

def populate_accounts_with_my_info_if_logged_in(accounts):
    account = load_account()
    if account is not None:
        seen_my_account = False
        for leaderboard_account in accounts:
            if leaderboard_account['account_id'] == account['id']:
                leaderboard_account['is_me'] = True
                seen_my_account = True
            else:
                leaderboard_account['is_me'] = False

        if not seen_my_account:
            score = calculate_import_score(account['id'], get_max_fave_count())
            accounts.append(make_account_display_data(account['id'], score))
    return accounts
