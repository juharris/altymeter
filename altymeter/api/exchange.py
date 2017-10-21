from abc import ABCMeta, abstractmethod


class TradingExchange(metaclass=ABCMeta):
    @abstractmethod
    def collect_data(self, pair: str, since=None, sleep_time=90):
        raise NotImplementedError

    @abstractmethod
    def create_order(self, pair: str, **kwargs) -> dict:
        raise NotImplementedError
