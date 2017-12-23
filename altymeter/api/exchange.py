from abc import ABCMeta, abstractmethod
from collections import namedtuple
from typing import List


class TradedPair(namedtuple('TradedPair', [
    'name',
    'exchange',
    'base',
    'base_full_name',
    'to',
    'to_full_name',
])):
    """
    A pair that is traded on an exchange.
    The price displayed in markets is a ratio where the `base` is used to buy the `to` asset.
    The following documentation will use CAD to ETH in Kraken as an example.

    :param name: The name of the pair traded (e.g. ETHCAD).
    :param exchange: The name of the exchange (e.g. Kraken).
    :param base: The asset used to buy and the asset obtained after selling.
                 (e.g. CAD)
                 (quote in the Kraken API and BaseCurrency in the Bittrex API).
    :param base_full_name: The full name of the `base` asset.
    :param to: The asset obtained after buying and the asset used to sell.
               (e.g. ETH)
               (base in the Kraken API and MarketCurrency in the Bittrex API).
    :param to_full_name: The full name of the `to` asset.
    """


class TradingExchange(metaclass=ABCMeta):
    @property
    @abstractmethod
    def name(self):
        raise NotImplementedError

    @abstractmethod
    def collect_data(self, pair: str, since=None, sleep_time=90, stop_event=None):
        raise NotImplementedError

    @abstractmethod
    def create_order(self, pair: str, **kwargs) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_traded_pairs(self) -> List[TradedPair]:
        raise NotImplementedError
