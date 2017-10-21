import logging
import sqlite3
import typing
from collections import Iterable, namedtuple, Sized
from operator import itemgetter
from typing import List, Optional, Union

import six
from injector import inject, ProviderOf, singleton
from tqdm import tqdm

from altymeter.module.constants import Configuration

Trade = namedtuple('Trade', ['price', 'amount', 'time'])
"""
A trade that was performed.
"""

DEFAULT_TIME_GROUPING = 60 * 10
"""
The default number of seconds to group transactions into.
"""


class SplitPrices(Iterable, Sized):
    """
    Prices over several consecutive periods.
    """

    def __init__(self, prices: list = None, volumes: list = None):
        self._prices = prices if prices else []
        self._times = []
        self._volumes = volumes if volumes else []

    def iter_prices(self):
        for chunk in self._prices:
            for price in chunk:
                yield price

    def get_num_chunks(self):
        return len(self._prices)

    @property
    def prices(self) -> List[List[float]]:
        return self._prices

    @property
    def times(self) -> List[List[float]]:
        return self._times

    @property
    def volumes(self) -> List[List[float]]:
        return self._volumes

    def __getitem__(self, item):
        return self.prices[item]

    def __iter__(self):
        return iter(self._prices)

    def __len__(self):
        return sum(map(len, self.prices))

    def __repr__(self):
        return repr(self._prices)

    def __str__(self):
        return str(self._prices)


@singleton
class PriceData(object):
    @inject
    def __init__(self, config: Configuration,
                 logger: logging.Logger,
                 db_provider: ProviderOf[sqlite3.Connection]):
        self._time_grouping = DEFAULT_TIME_GROUPING
        pricing_config = config.get('pricing')
        if pricing_config:
            self._time_grouping = pricing_config.get('time grouping', self._time_grouping)

        self._logger = logger
        self._db_provider = db_provider

    def add_prices(self, pair: str, trades: List[Trade]):
        db = None
        try:
            db = self._db_provider.get()
            cursor = db.cursor()
            prices = []
            for trade in trades:
                prices.append((pair, trade.price, trade.amount, trade.time))
            cursor.executemany('INSERT INTO trade VALUES ('
                               '?, ?, ?, ?)', prices)
            db.commit()
        finally:
            if db:
                db.close()

    def get_pairs(self) -> List[str]:
        """
        :return: All pairs in the database.
        """
        db = None
        try:
            db = self._db_provider.get()
            cursor = db.cursor()
            result = cursor.execute('SELECT DISTINCT pair FROM trade')
            result = list(map(itemgetter(0), result))
        finally:
            if db:
                db.close()
        return result

    def get_prices(self, pairs: Union[str, typing.Iterable[str]] = None) -> SplitPrices:
        """
        :param pairs: The traded pairs to get prices for.
        :return: Prices grouped by time intervals.
        """
        result = SplitPrices()
        if pairs is None:
            pairs = self.get_pairs()
        elif isinstance(pairs, six.string_types):
            pairs = [pairs]

        self._logger.info("Getting prices for: %s", pairs)

        for pair in pairs:
            current_prices = []
            current_times = []
            current_volumes = []

            prev_time_class = None
            grouped_trades = 0
            total_trade_amount_in_group = 0

            for trade in self.get_trades(pair):
                price = trade.price
                amount = trade.amount
                time_class = int(trade.time / self._time_grouping)

                if prev_time_class == time_class or prev_time_class is None:
                    grouped_trades += amount * price
                    total_trade_amount_in_group += amount
                else:
                    current_prices.append(grouped_trades / total_trade_amount_in_group)
                    current_times.append((time_class + 0.5) * self._time_grouping)
                    current_volumes.append(total_trade_amount_in_group)
                    grouped_trades = amount * price
                    total_trade_amount_in_group = amount
                    if prev_time_class + 1 != time_class:
                        # Split since trades are not consecutive.
                        result.prices.append(current_prices)
                        result.times.append(current_times)
                        result.volumes.append(current_volumes)
                        current_prices = []
                        current_times = []
                        current_volumes = []

                prev_time_class = time_class

            if total_trade_amount_in_group:
                current_prices.append(grouped_trades / total_trade_amount_in_group)
                current_times.append((time_class + 0.5) * self._time_grouping)
                current_volumes.append(total_trade_amount_in_group)
                result.prices.append(current_prices)
                result.times.append(current_times)
                result.volumes.append(current_volumes)

        return result

    def get_trades(self, pair: str, since: Optional[float] = None) -> List[Trade]:
        """
        :param pair: The traded pair to get trades for.
        :param since: Time (in seconds) to get trades since.
        :return: Recorded trades sorted in chronological order by time.
        """
        db = None
        try:
            db = self._db_provider.get()
            cursor = db.cursor()
            result = []
            if since is None:
                trades = cursor.execute('SELECT * FROM trade WHERE pair = ? '
                                        'ORDER BY time ASC', (pair,))
            else:
                trades = cursor.execute('SELECT * FROM trade WHERE pair = ? '
                                        'AND time >= ? '
                                        'ORDER BY time ASC', (pair, since,))
            for trade in tqdm(trades, desc="Getting trades for %s" % pair,
                              unit_scale=True, mininterval=2, unit=" trades"):
                result.append(Trade(trade[1], trade[2], trade[3]))
        finally:
            if db:
                db.close()
        return result

    def has_continuous_trades_since(self, pair: str, since: float) -> bool:
        """
        :param pair: The traded pair to check.
        :param since: Time (in seconds) to check for continuous trades.
        :return:
        """
        db = None
        try:
            db = self._db_provider.get()
            cursor = db.cursor()

            trades = cursor.execute('SELECT * FROM trade '
                                    'WHERE pair = ? AND time >= ?'
                                    'ORDER BY time ASC', (pair, since,))
            result = True

            prev_time_class = None
            for trade in trades:
                trade_time = trade[3]
                time_class = int(trade_time / self.time_grouping)

                # TODO Check first.
                if prev_time_class is None:
                    since_time_class = int(since / self.time_grouping)
                    if time_class != since_time_class:
                        result = False
                        break
                elif prev_time_class + 1 < time_class:
                    # Not continuous.
                    result = False
                    break
                prev_time_class = time_class

            if prev_time_class is None:
                # No data found or broke early.
                result = False
        finally:
            if db:
                db.close()
        return result

    @property
    def time_grouping(self):
        return self._time_grouping
