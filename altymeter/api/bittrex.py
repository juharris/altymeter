import hashlib
import hmac
import json
import time
from logging import Logger
from typing import List, Optional
from urllib.parse import urlencode

import requests
from injector import inject, singleton

from altymeter.api.exchange import (ExchangeOrder,
                                    PairRecentStats,
                                    TradedPair,
                                    TradingExchange)
from altymeter.module.constants import Configuration


@singleton
class BittrexApi(TradingExchange):
    """
    https://bittrex.com/Home/Api
    """

    _url_base = 'https://bittrex.com/api/v1.1/%s/%s?apikey=%s&nonce=%d'

    _account_methods = {}
    _market_methods = {'buylimit', 'cancel', 'getopenorders', 'selllimit'}

    @inject
    def __init__(self, config: Configuration, logger: Logger):
        self._logger = logger

        config = config['exchanges']['Bittrex']
        self._api_key = config['api key']
        self._api_secret = config['api secret']

    @property
    def name(self):
        return "Bittrex"

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

    def collect_data(self, pair: str, since=None, sleep_time=90, stop_event=None):
        raise NotImplementedError()

    def create_order(self, pair: str,
                     action_type: str, order_type: str,
                     volume: float,
                     price: Optional[float] = None,
                     **kwargs) -> ExchangeOrder:
        assert action_type in ['buy', 'sell']
        assert price is not None, "`price` is required for Bittrex."
        assert order_type == 'limit', "Only limit is supported for Bittrex."
        # TODO Support market orders by checking prices.
        action_type = action_type.lower()

        volume = '{:.8f}'.format(volume)

        params = dict(market=pair,
                      quantity=volume)
        if price is not None:
            if not isinstance(price, str):
                # TODO Determine num decimals required for pair.
                price = '{:.8f}'.format(price)
            params['rate'] = price
        self._logger.info(f"{action_type} {order_type} {volume} {pair} @{price}")
        self._request('{}{}'.format(action_type, order_type), params)

        return ExchangeOrder(pair, self.name,
                             price=float(price),
                             volume=float(volume),
                             # Order created if we got here.
                             status='CREATED',
                             action_type=action_type,
                             order_type=order_type
                             )

    def get_currencies(self):
        return self._request('getcurrencies')

    def get_market_history(self, market):
        return self._request('getmarkethistory', dict(market=market))

    def get_market_summaries(self):
        return self._request('getmarketsummaries')

    def get_recent_stats(self, pair: str) -> PairRecentStats:
        stats = self._request('getmarketsummary', dict(market=pair))
        stats = stats.get('result')
        if isinstance(stats, list):
            assert len(stats) > 0
            stats = stats[0]
        return PairRecentStats(name=pair,
                               exchange=self.name,
                               weighted_avg_price=None,
                               last_price=float(stats['Last']),
                               )

    def get_ticker(self, market):
        return self._request('getticker', dict(market=market))

    def get_traded_pairs(self) -> List[TradedPair]:
        # TODO Cache.
        result = []
        markets = self._request('getmarkets')
        for market in markets['result']:
            if market['IsActive']:
                result.append(TradedPair(market['MarketName'],
                                         self.name,
                                         base=market['BaseCurrency'],
                                         base_full_name=market['BaseCurrencyLong'],
                                         to=market['MarketCurrency'],
                                         to_full_name=market['MarketCurrencyLong']
                                         ))
        return result
