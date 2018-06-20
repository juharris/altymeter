import threading
from logging import Logger
from typing import Dict

from injector import inject, singleton

from altymeter.api.exchange import TradingExchange
from altymeter.module.constants import Configuration


@singleton
class DataCollector(object):
    @inject
    def __init__(self, config: Configuration,
                 exchanges: Dict[str, TradingExchange],
                 logger: Logger):
        self._exchanges = exchanges
        self._logger = logger

        self._exchanges_config = config['exchanges']

    def collect_data(self):
        for exchange_name, conf in self._exchanges_config.items():
            pairs = conf.get('collect')
            if pairs is None:
                continue
            exchange = self._exchanges[exchange_name]
            for pair in pairs:
                base, to = pair.split(',')
                pair = exchange.get_pair(base=base, to=to)
                if pair is None:
                    raise Exception(f"Could not find {base} to {to} in {exchange_name}.\nTraded pairs: " +
                                    "\n".join(map(str, exchange.get_traded_pairs())))

                thread_name = f"collect_{exchange.name}_{pair}"
                thread = threading.Thread(target=lambda: exchange.collect_data(pair),
                                          name=thread_name)
                thread.start()


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    inj = AltymeterModule.get_injector()
    d: DataCollector = inj.get(DataCollector)
    d.collect_data()
