import socket
from logging import Logger

import requests
from injector import inject, singleton

from altymeter.module.constants import Configuration


@singleton
class CryptoCompareApi(object):
    @inject
    def __init__(self, config: Configuration,
                 logger: Logger):
        self._config = config
        self._logger = logger

        self._metric_keys = ['close', 'high', 'low', 'open']

    def get_hour_value(self, symbol: str, fiat_symbol: str, time_in_s: float) -> float:
        app_name = f'{socket.gethostname()}-altymeter'
        time_in_s = int(time_in_s)
        params = {
            'fsym': symbol,
            'tsym': fiat_symbol,
            'limit': 1,
            'aggregate': 1,
            'toTs': time_in_s,
            'extraParams': app_name,
        }
        r = requests.get('https://min-api.cryptocompare.com/data/histohour', params)
        r.raise_for_status()
        response = r.json()
        assert response['Response'] == 'Success', response
        data = response['Data']
        assert len(data) > 0
        last_entry = data[-1]
        result = sum([last_entry[key] for key in self._metric_keys]) / 4
        return result


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule
    import time

    injector = AltymeterModule.get_injector()
    c: CryptoCompareApi = injector.get(CryptoCompareApi)

    v = c.get_hour_value('NEO', 'CAD', int(time.time()))
    print(v)
