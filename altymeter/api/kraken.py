import hashlib
import hmac
import json
import logging
import threading
import time
from base64 import b64decode, b64encode
from logging import Logger
from typing import List, Optional
from urllib.parse import urlencode

import requests
from expiringdict import ExpiringDict
from injector import inject, singleton
from tqdm import tqdm

from altymeter.api.exchange import (ExchangeOpenOrder,
                                    PairRecentStats,
                                    TradedPair,
                                    TradingExchange)
from altymeter.module.constants import Configuration
from altymeter.pricing import PriceData, Trade


@singleton
class KrakenApi(TradingExchange):
    """
    https://www.kraken.com/help/api
    """

    _url_base = 'https://api.kraken.com'
    _api_version = '0'

    @inject
    def __init__(self, config: Configuration,
                 logger: Logger,
                 price_data: PriceData,
                 ):
        config = config['exchanges']['Kraken']
        self._api_key = config['api key']
        self._api_secret = config['api secret']

        self._logger = logger
        self._price_data = price_data

        self._traded_pairs_cache = ExpiringDict(max_len=1, max_age_seconds=24 * 60 * 60)

    @property
    def name(self):
        return "Kraken"

    def _request(self, method, data=None, timeout=5):
        nonce = int(time.time() * 1000)

        url_path = '/%s/%s' % (self._api_version, method)

        if data:
            data = {k: v for (k, v) in data.items() if v is not None}
            data['nonce'] = nonce
        else:
            data = dict(nonce=nonce)

        msg = (str(nonce) + urlencode(data)).encode()
        msg = url_path.encode() + hashlib.sha256(msg).digest()

        api_sign = hmac.new(b64decode(self._api_secret),
                            msg,
                            hashlib.sha512)
        api_sign = b64encode(api_sign.digest())

        r = requests.post(self._url_base + url_path,
                          data=data,
                          headers={
                              'API-Key': self._api_key,
                              'API-Sign': api_sign.decode(),
                          },
                          timeout=timeout)
        r.raise_for_status()
        result = r.json()
        if self._logger.isEnabledFor(logging.DEBUG):
            resp_str = json.dumps(result, indent=2)
            if len(resp_str) < 200:
                self._logger.debug("%s response:\n%s", method, resp_str)
        if result.get('error'):
            raise Exception("Error calling server.\nData:%s\nResponse:\n%s" %
                            (json.dumps(data, indent=2), json.dumps(result, indent=2)))
        return result

    def cancel(self, transaction_id):
        return self._request('private/CancelOrder', dict(txid=transaction_id))

    def collect_data(self, pair: str, since: int = None, sleep_time=90, stop_event: threading.Event = None):
        self._logger.info("Collecting data for %s since %s.", pair, since)
        with tqdm(desc="Collecting data for %s" % pair,
                  unit=" trades", unit_scale=True) as progress_bar:
            while True:
                if stop_event is not None and stop_event.is_set():
                    self._logger.info("Got signal to stop collecting %s.", pair)
                    break
                try:
                    r = self.get_market_history(pair, since)
                    pair_result = r.get('result')
                    pair_trades = pair_result.get(pair)
                    if pair_trades:
                        trades = []
                        for trade in pair_trades:
                            price = float(trade[0])
                            amount = float(trade[1])
                            trade_time = trade[2]
                            trades.append(Trade(price, amount, trade_time))
                        # Note that duplicate data will fail to insert here but it's okay
                        # because eventually new trades will be found soon.
                        # Even if `since` is specified, the API ignores very old `since` values.
                        self._price_data.add_prices(pair, trades)
                        progress_bar.update(len(trades))
                    since = pair_result.get('last')
                    time.sleep(sleep_time)
                except:
                    self._logger.exception("Error getting trades.")
                    time.sleep(sleep_time / 3)
                    # Don't allow yielding since there are no new trades.

    def create_order(self, pair, action_type, order_type, volume,
                     price: Optional[str] = None,
                     expire_time_s=None,
                     **kwargs) -> dict:
        data = dict(pair=pair,
                    type=action_type,
                    ordertype=order_type,
                    volume=volume,
                    )
        if price:
            data['price'] = price
        if expire_time_s is not None:
            data['expiretm'] = expire_time_s

        data.update(kwargs)
        if data.get('validate') == False:
            del data['validate']
        # TODO Convert to ExchangeOrder.
        return self._request('private/AddOrder', data)

    def get_account_balances(self) -> dict:
        result = self._request('private/Balance')
        result = result.get('result')
        result = {k: float(v) for (k, v) in result.items()}
        return result

    def get_currencies(self):
        raise NotImplementedError

    def get_markets(self):
        raise NotImplementedError

    def get_market_history(self, pair, since=None):
        """

        :param pair:
        :param since: In nanoseconds.
        :return:
        """
        params = dict(pair=pair)
        if since:
            params['since'] = since
        return self._request('public/Trades', params)

    def get_open_orders(self, trades=False, userref=None):
        return self._request('private/OpenOrders')

    def get_order_book(self, pair: Optional[str] = None,
                       base: Optional[str] = None, to: Optional[str] = None,
                       order_type: Optional[str] = 'all') \
            -> List[ExchangeOpenOrder]:
        result = []
        pair = self.get_pair(pair, base, to)
        data = dict(pair=pair)
        orders = self._request('public/Depth', data, timeout=7)
        for order_dict in orders['result'].values():
            if order_type != 'bid':
                for order in order_dict['asks']:
                    result.append(ExchangeOpenOrder(
                        pair, self.name,
                        price=float(order[0]),
                        volume=float(order[1]),
                        order_type='ask'
                    ))
            if order_type != 'ask':
                for order in order_dict['bids']:
                    result.append(ExchangeOpenOrder(
                        pair, self.name,
                        price=float(order[0]),
                        volume=float(order[1]),
                        order_type='bid'
                    ))

        return result

    def get_pair(self, pair: Optional[str] = None,
                 base: Optional[str] = None, to: Optional[str] = None) -> str:
        result = pair
        if result is None:
            assert base is not None and to is not None
            # Kraken has tricky combination rules with fiat currencies so it's easiest to just check all pairs.
            for tp in self.get_traded_pairs():
                if tp.base == base and tp.to == to:
                    result = tp.name
                    break
        else:
            assert base is None and to is None
        return result

    def get_recent_stats(self, pair: str) -> PairRecentStats:
        raise NotImplementedError

    def get_ticker(self, market):
        raise NotImplementedError

    def get_traded_pairs(self) -> List[TradedPair]:
        key = 'traded_pairs'
        result = self._traded_pairs_cache.get(key)
        if result:
            return result
        result = []
        markets = self._request('public/AssetPairs', timeout=15)
        markets = markets.get('result') or []
        for market in markets.values():
            result.append(TradedPair(
                name=market.get('altname'),
                exchange=self.name,
                base=market.get('quote'),
                base_full_name=market.get('quote'),
                to=market.get('base'),
                to_full_name=market.get('base'),
            ))
        self._traded_pairs_cache[key] = result
        return result


if __name__ == '__main__':
    import sys
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()
    k = injector.get(KrakenApi)
    """
    :type: KrakenApi
    """

    pair = sys.argv[1]
    since = sys.argv[2] if len(sys.argv) > 2 else None
    k.collect_data(pair, since)
