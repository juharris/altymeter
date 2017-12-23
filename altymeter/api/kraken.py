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
from injector import inject
from tqdm import tqdm

from altymeter.api.exchange import TradedPair, TradingExchange
from altymeter.module.constants import Configuration
from altymeter.pricing import PriceData, Trade


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

    @property
    def name(self):
        return "Kraken"

    def _request(self, method, data=None):
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
                          timeout=60)
        r.raise_for_status()
        result = r.json()
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("Response:\n%s", json.dumps(result, indent=2))
        if result.get('error'):
            raise Exception("Error calling server. Response:\n%s" % json.dumps(result, indent=2))
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

    def create_order(self, pair, type, order_type, volume,
                     price: Optional[str] = None,
                     expire_time_s=None,
                     **kwargs):
        data = dict(pair=pair,
                    type=type,
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
        return self._request('private/AddOrder', data)

    def get_account_balances(self) -> dict:
        result = self._request('private/Balance')
        result = result.get('result')
        result = {k: float(v) for (k, v) in result.items()}
        return result

    def get_currencies(self):
        return self._request('')

    def get_markets(self):
        return self._request('')

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

    def get_market_summaries(self):
        return self._request('')

    def get_market_summary(self, market):
        return self._request('', dict(market=market))

    def get_open_orders(self, trades=False, userref=None):
        return self._request('private/OpenOrders')

    def get_ticker(self, market):
        return self._request('', dict(market=market))

    def get_traded_pairs(self) -> List[TradedPair]:
        # TODO Cache.
        result = []
        markets = self._request('public/AssetPairs')
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
