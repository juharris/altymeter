import os
from logging import Logger
from typing import List, Optional

import numpy as np
import pandas as pd
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
class QuadrigaCxApi(TradingExchange):
    """
    """

    @inject
    def __init__(self, config: Configuration,
                 logger: Logger,
                 price_data: PriceData,
                 ):
        config = config['exchanges'].get('QuadrigaCX') or dict()

        self._logger = logger
        self._price_data = price_data
        self._traded_pairs_cache = ExpiringDict(max_len=1, max_age_seconds=24 * 60 * 60)

    @property
    def name(self):
        return "QuadrigaCX"

    def collect_data(self, pair: str, since=None, sleep_time=90, stop_event=None):
        raise NotImplementedError

    def convert_actions(self, dir_path: str) -> pd.DataFrame:
        result = []
        for path in os.listdir(dir_path):
            path = os.path.join(dir_path, path)
            data = pd.read_csv(path,
                               parse_dates=['datetime'],
                               )

            if 'fundings' in path:
                net_amount_index = data.columns.get_loc('net amount') + 1
                for row in data.itertuples():
                    quantity = row.gross
                    if np.isnan(quantity):
                        quantity = row[net_amount_index]
                    if isinstance(row.address, str):
                        wallet = row.address
                        from_exchange = 'Local Wallet'
                    else:
                        wallet = None
                        from_exchange = None
                    currency = row.currency.upper()
                    result.append({
                        'Date': row.datetime,
                        'Type': 'Transfer',
                        'Quantity': quantity,
                        'Currency': currency,
                        'Exchange': from_exchange,
                        'Wallet': wallet,
                        'Price': quantity,
                        'Currency.1': currency,
                        'Exchange.1': self.name,
                        'Wallet.1': None,
                        'Disabled': None,
                    })
            elif 'trades' in path:
                for row in data.itertuples():
                    if row.type == 'buy':
                        from_currency = row.minor.upper()
                        to_currency = row.major.upper()
                        price = row.value
                    elif row.type == 'sell':
                        from_currency = row.major.upper()
                        to_currency = row.minor.upper()
                        price = row.amount
                    else:
                        raise ValueError(f"Invalid row type: {row.type}\nfor row: {row}")
                    result.append({
                        'Date': row.datetime,
                        'Type': 'Trade',
                        'Quantity': row.total,
                        'Currency': to_currency,
                        'Exchange': self.name,
                        'Wallet': f'{to_currency} Wallet',
                        'Price': price,
                        'Currency.1': from_currency,
                        'Exchange.1': self.name,
                        'Wallet.1': f'{from_currency} Wallet',
                        'Disabled': None,
                    })
            elif 'withdrawals' in path:
                for row in data.itertuples():
                    if isinstance(row.address, str):
                        wallet = row.address
                        to_exchange = 'Local Wallet'
                    else:
                        wallet = None
                        to_exchange = None
                    currency = row.currency.upper()
                    result.append({
                        'Date': row.datetime,
                        'Type': 'Transfer',
                        'Quantity': row.amount,
                        'Currency': currency,
                        'Exchange': self.name,
                        'Wallet': f'{currency} Wallet',
                        'Price': row.amount,
                        'Currency.1': currency,
                        'Exchange.1': to_exchange,
                        'Wallet.1': wallet,
                        'Disabled': None,
                    })

        result = pd.DataFrame(result)
        return result

    def create_order(self, pair: str,
                     action_type: str,
                     order_type: str,
                     volume: float,
                     price: Optional[float] = None,
                     **kwargs) -> ExchangeOrder:
        raise NotImplementedError

    def get_deposit_history(self) -> List[ExchangeTransfer]:
        raise NotImplementedError

    def get_order_book(self, pair: Optional[str] = None,
                       base: Optional[str] = None, to: Optional[str] = None,
                       order_type: Optional[str] = 'all') \
            -> List[ExchangeOpenOrder]:
        raise NotImplementedError

    def get_pair(self, pair: Optional[str] = None,
                 base: Optional[str] = None, to: Optional[str] = None) -> str:
        raise NotImplementedError

    def get_recent_stats(self, pair: str) -> PairRecentStats:
        raise NotImplementedError

    def get_traded_pairs(self) -> List[TradedPair]:
        raise NotImplementedError

    def get_withdrawal_history(self) -> List[ExchangeTransfer]:
        raise NotImplementedError


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()
    q: QuadrigaCxApi = injector.get(QuadrigaCxApi)
