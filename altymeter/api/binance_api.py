import threading
from logging import Logger
from typing import List, Optional

from binance.client import Client as BinanceClient
from expiringdict import ExpiringDict
from injector import inject, singleton

from altymeter.api.exchange import (ExchangeOpenOrder,
                                    ExchangeOrder,
                                    ExchangeTransfer,
                                    PairRecentStats,
                                    TradedPair,
                                    TradingExchange)
from altymeter.module.constants import Configuration
from altymeter.pricing import PriceData


@singleton
class BinanceApi(TradingExchange):
    """
    https://github.com/sammchardy/python-binance
    """

    @inject
    def __init__(self, config: Configuration,
                 logger: Logger,
                 price_data: PriceData,
                 ):
        config = config['exchanges']['Binance']
        self._binance = BinanceClient(config['api key'], config['api secret'])

        self._logger = logger
        self._price_data = price_data
        self._traded_pairs_cache = ExpiringDict(max_len=1, max_age_seconds=24 * 60 * 60)

    @property
    def name(self):
        return "Binance"

    def collect_data(self, pair: str, since: int = None, sleep_time=90,
                     stop_event: threading.Event = None):
        raise NotImplementedError

    def create_order(self, pair: str,
                     action_type: str, order_type: str,
                     volume: float,
                     price: Optional[float] = None,
                     **kwargs) -> ExchangeOrder:
        action_type = action_type.lower()
        if action_type == 'buy':
            side = BinanceClient.SIDE_BUY
        elif action_type == 'sell':
            side = BinanceClient.SIDE_SELL
        else:
            raise ValueError("Invalid action_type: \'{}\'".format(action_type))

        order_types = dict(
            LIMIT=BinanceClient.ORDER_TYPE_LIMIT,
            MARKET=BinanceClient.ORDER_TYPE_MARKET,
            STOP_LOSS=BinanceClient.ORDER_TYPE_STOP_LOSS,
            STOP_LOSS_LIMIT=BinanceClient.ORDER_TYPE_STOP_LOSS_LIMIT,
            TAKE_PROFIT=BinanceClient.ORDER_TYPE_TAKE_PROFIT,
            TAKE_PROFIT_LIMIT=BinanceClient.ORDER_TYPE_TAKE_PROFIT_LIMIT,
            LIMIT_MAKER=BinanceClient.ORDER_TYPE_LIMIT_MAKER,
        )
        order_type = order_types.get(order_type.upper())
        if not order_type:
            raise ValueError("Invalid order_type: \'{}\'"
                             "Valid order types are: {}\n".format(order_type, order_types.keys()))

        time_in_force = kwargs.get('time_in_force', BinanceClient.TIME_IN_FORCE_IOC)

        volume = '{:.8f}'.format(volume)

        params = dict(
            timeInForce=time_in_force,
            symbol=pair,
            side=side,
            type=order_type,
            quantity=volume,
        )
        if price is not None:
            if not isinstance(price, str):
                # TODO Determine num decimals required for pair.
                price = '{:.8f}'.format(price)
            params['price'] = price

        self._logger.info(f"{side} {order_type} {volume} {pair} @{price}")
        # TODO Look into using create_test_order `if kwargs.get('validate')`.
        resp = self._binance.create_order(**params)
        self._logger.debug("Order response: %s", resp)
        self._logger.info("Order status: %s", resp.get('status'))
        return ExchangeOrder(
            pair,
            self.name,
            float(resp['price']),
            float(resp['origQty']),
            resp['status'],
            action_type=resp['side'].lower(),
            order_type=resp['type'].lower(),
        )

    def get_deposit_history(self) -> List[ExchangeTransfer]:
        raise NotImplementedError

    def get_order_book(self, pair: Optional[str] = None,
                       base: Optional[str] = None, to: Optional[str] = None,
                       order_type: Optional[str] = 'all') \
            -> List[ExchangeOpenOrder]:
        pair = self.get_pair(pair, base, to)
        result = []
        orders = self._binance.get_order_book(symbol=pair)
        if order_type != 'bid':
            for order in orders['asks']:
                result.append(ExchangeOpenOrder(
                    pair, self.name,
                    price=float(order[0]),
                    volume=float(order[1]),
                    order_type='ask'
                ))
        if order_type != 'ask':
            for order in orders['bids']:
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
            result = '{}{}'.format(to, base)
        else:
            assert base is None and to is None
        return result

    def get_recent_stats(self, pair: str) -> PairRecentStats:
        recent_stats = self._binance.get_ticker(symbol=pair)
        return PairRecentStats(name=pair,
                               exchange=self.name,
                               weighted_avg_price=float(recent_stats['weightedAvgPrice']),
                               last_price=float(recent_stats['lastPrice']),
                               )

    def get_traded_pairs(self) -> List[TradedPair]:
        key = 'traded_pairs'
        result = self._traded_pairs_cache.get(key)
        if result:
            return result
        # TODO Get full names from another API like coinmarketcap.
        result = []
        for symbol in self._binance.get_exchange_info()['symbols']:
            if symbol['status'] == 'TRADING':
                result.append(TradedPair(name=symbol['symbol'],
                                         exchange=self.name,
                                         base=symbol['quoteAsset'],
                                         base_full_name=symbol['quoteAsset'],
                                         to=symbol['baseAsset'],
                                         to_full_name=symbol['baseAsset']))

        self._traded_pairs_cache[key] = result
        return result

    def get_withdrawal_history(self) -> List[ExchangeTransfer]:
        raise NotImplementedError


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()
    b = injector.get(BinanceApi)
    """:type: BinanceApi"""
