import hashlib
import hmac
import json
import time
from logging import Logger
from typing import List, Optional
from urllib.parse import urlencode

import requests
from expiringdict import ExpiringDict
from injector import inject, singleton

from altymeter.api.exchange import (ExchangeOpenOrder,
                                    ExchangeOrder,
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

        self._traded_pairs_cache = ExpiringDict(max_len=1, max_age_seconds=24 * 60 * 60)

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

    def get_market_summaries(self):
        return self._request('getmarketsummaries')

    def get_order_book(self, pair: Optional[str] = None,
                       base: Optional[str] = None, to: Optional[str] = None,
                       order_type: Optional[str] = 'all') \
            -> List[ExchangeOpenOrder]:
        result = []
        pair = self.get_pair(pair, base, to)
        if order_type == 'buy':
            order_type = 'bid'
        elif order_type == 'sell':
            order_type = 'ask'
        else:
            order_type = 'both'
        orders = self._request('getorderbook', dict(market=pair, type=order_type))
        orders = orders['result']
        buy_orders = orders.get('buy')
        if buy_orders:
            for order in buy_orders:
                result.append(ExchangeOpenOrder(
                    pair, self.name,
                    price=order['Rate'],
                    volume=order['Quantity'],
                    order_type='bid'
                ))
        sell_orders = orders.get('sell')
        if sell_orders:
            for order in sell_orders:
                result.append(ExchangeOpenOrder(
                    pair, self.name,
                    price=order['Rate'],
                    volume=order['Quantity'],
                    order_type='ask'
                ))
        return result

    def get_pair(self, pair: Optional[str] = None,
                 base: Optional[str] = None, to: Optional[str] = None) -> str:
        result = pair
        if result is None:
            assert base is not None and to is not None
            result = '{}-{}'.format(base, to)
        else:
            assert base is None and to is None
        return result

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
        key = 'traded_pairs'
        result = self._traded_pairs_cache.get(key)
        if result:
            return result
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
        self._traded_pairs_cache[key] = result
        return result
