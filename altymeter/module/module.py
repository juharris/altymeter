import logging
import os
from typing import Dict

import yaml
from injector import Binder, Injector, Module, provider, singleton

from altymeter.api.binance_api import BinanceApi
from altymeter.api.bittrex import BittrexApi
from altymeter.api.exchange import TradingExchange
from altymeter.api.kraken import KrakenApi
from altymeter.module.constants import Configuration, user_dir
from altymeter.module.db_module import DbModule


class AltymeterModule(Module):
    _injector = None

    @classmethod
    def get_injector(cls) -> Injector:
        """
        :return: An `Injector` for production.
        """
        if cls._injector is None:
            cls._injector = Injector([cls,
                                      DbModule,
                                      ])
        return cls._injector

    @singleton
    @provider
    def provide_config(self) -> Configuration:
        try:
            path = os.path.join(user_dir, 'config.yaml')
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                logging.warning("Config does not exist. A default one will be created at `%s`.\n"
                                "See the README for how to fill it in.", path)
                default = {
                    'API': {
                        'Twitter': {
                            'access token key': 'TODO',
                            'access token secret': 'TODO',
                            'consumer key': 'TODO',
                            'consumer secret': 'TODO',
                        },
                        'Pushbullet': {
                            'api key': 'TODO',
                            'device name': 'TODO',
                            'encryption password': 'TODO',
                        },
                    },
                    'exchanges': dict(Kraken=dict(api_key='TODO', api_secret='TODO')),
                    'default exchange': 'Kraken',
                    'log level': logging.getLevelName(logging.INFO),
                    'pricing': {
                        'time grouping': 10 * 60,
                    },
                    'DB connection': os.path.join(user_dir, 'altymeter.db'),
                    'trading': {
                        'dry run': False,
                        'plot data': True,
                    },
                    'training': {
                        'epochs': 10,
                        'plot data': False,
                    },
                }
                with open(path, 'w') as f:
                    yaml.dump(default, f, default_flow_style=False)
            with open(path) as f:
                return yaml.load(f)
        except:
            logging.exception("Error loading configuration.")
            raise

    @singleton
    @provider
    def provide_logger(self, config: Configuration) -> logging.Logger:
        result = logging.getLogger('altymeter')
        log_level = config.get('log level', logging.INFO)
        result.setLevel(log_level)
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(name)s:%(filename)s:%(funcName)s\n%(message)s')
        ch.setFormatter(formatter)
        result.addHandler(ch)
        return result

    @singleton
    @provider
    def provide_exchange(self, config: Configuration,
                         exchanges: Dict[str, TradingExchange]) -> TradingExchange:
        exchange = config.get('default exchange')
        if not exchange:
            exchanges = config.get('exchanges')
            if len(exchanges) == 0:
                raise Exception("You must put an exchange in your configuration.")
            if len(exchanges) == 1:
                exchange = next(iter(exchanges.keys()))
        if not exchange:
            raise Exception("Could not determine the default exchange."
                            "\nSpecify a `default exchange` in your configuration.")
        normalized_exchange_name = exchange.lower()
        result = exchanges.get(normalized_exchange_name)
        if not result:
            raise Exception("Non supported exchange: \"{}\" or it's not in your configuration.".format(exchange))
        return result

    @singleton
    @provider
    def provide_exchanges(self, config: Configuration,
                          inj: Injector) -> Dict[str, TradingExchange]:
        result = dict()
        exchanges = config.get('exchanges')
        exchange_names = set(map(str.lower, exchanges.keys()))
        if 'binance' in exchange_names:
            b = inj.get(BinanceApi)
            result[b.name] = b
            result['binance'] = b
        if 'bittrex' in exchange_names:
            b = inj.get(BittrexApi)
            result[b.name] = b
            result['bittrex'] = b
        if 'kraken' in exchange_names:
            k = inj.get(KrakenApi)
            result[k.name] = k
            result['kraken'] = k
        return result

    def configure(self, binder: Binder):
        pass
