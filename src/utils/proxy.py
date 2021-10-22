import random
import logging
import src.utils.utils as utils

from flask import current_app

def get_proxy():
    proxies = utils.get_value(current_app.config, 'PROXIES')
    if proxies and len(proxies):
        proxy = random.choice(proxies)
        return {
            "http": proxy,
            "https": proxy
        }
    else:
        raise Exception('No proxies defined')
