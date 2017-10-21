import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import requests
from injector import inject

from altymeter.api.exchange import TradingExchange
from altymeter.module.constants import Configuration


class BittrexApi(TradingExchange):
    """
    https://bittrex.com/Home/Api
    """

    _url_base = 'https://bittrex.com/api/v1.1/%s/%s?apikey=%s&nonce=%d'

    _account_methods = {}
    _market_methods = {'buylimit', 'cancel', 'getopenorders', 'selllimit'}

    @inject
    def __init__(self, config: Configuration):
        config = config['exchanges']['Bittrex']
        self._api_key = config['api key']
        self._api_secret = config['api secret']

    def _request(self, method, params=None):
        if method in self._account_methods:
            method_type = 'account'
        elif method in self._market_methods:
            method_type = 'market'
        else:
            method_type = 'public'

        nonce = int(time.time() * 1000)

        url = self._url_base % (method_type, method, self._api_key, nonce)

        if params:
            url += '&'
            url += urlencode(params)

        apisign = hmac.new(self._api_secret.encode(), url.encode(), hashlib.sha512).hexdigest()

        r = requests.get(url,
                         headers=dict(apisign=apisign))
        r.raise_for_status()
        result = r.json()
        if result.get('success') != True:
            raise Exception("Error calling server. Response:\n%s" % json.dumps(result, indent=2))
        return result

    def cancel(self, order_uuid):
        return self._request('cancel', dict(uuid=order_uuid))

    def get_currencies(self):
        return self._request('getcurrencies')

    def get_markets(self):
        return self._request('getmarkets')

    def get_market_history(self, market):
        return self._request('getmarkethistory', dict(market=market))

    def get_market_summaries(self):
        return self._request('getmarketsummaries')

    def get_market_summary(self, market):
        return self._request('getmarketsummary', dict(market=market))

    def get_ticker(self, market):
        return self._request('getticker', dict(market=market))
