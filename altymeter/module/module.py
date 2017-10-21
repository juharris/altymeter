import logging
import os

import yaml
from injector import Binder, Injector, Module, provider, singleton

from altymeter.api.exchange import TradingExchange
from altymeter.api.kraken import KrakenApi
from altymeter.module.constants import Configuration, user_dir
from altymeter.module.db_module import DbModule


class AltymeterModule(Module):
    _injector = None

    @classmethod
    def get_injector(cls):
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
                    'exchanges': dict(Kraken=dict(api_key='TODO', api_secret='TODO')),
                    'log level': logging.getLevelName(logging.INFO),
                    'pricing': {
                        'time grouping': 10 * 60,
                    },
                    'DB connection': os.path.join(user_dir, 'altymeter.db'),
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

    def configure(self, binder: Binder):
        binder.bind(TradingExchange, KrakenApi, scope=singleton)
