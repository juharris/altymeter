import os
import time
from collections import defaultdict
from logging import Logger
from operator import itemgetter
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from bidict import bidict
from injector import inject, singleton
from tqdm import tqdm

from altymeter.api.exchange import TradingExchange
from altymeter.module.constants import Configuration
from altymeter.pricing import PriceData

seconds_per_day = 24 * 60 * 60

trade_types = {'Bought', 'Sold', 'Trade'}


class DigitalAssetHodling(object):
    def __init__(self):
        self._amount = 0
        self._cost_of_amount = 0
        # Grouped by year.
        self._total_cost_of_amount_sold = defaultdict(float)
        # Grouped by year.
        self._proceeds = defaultdict(float)

    def __isub__(self, amount: float):
        assert isinstance(amount, float)
        assert self._amount > 0
        self._cost_of_amount *= (self._amount - amount) / self._amount
        self._amount -= amount
        return self

    @property
    def amount(self):
        return self._amount

    @property
    def avg_cost(self):
        if self._amount != 0:
            return self._cost_of_amount / self._amount
        else:
            return 0

    def add(self, amount: float, cost: float):
        self._amount += amount
        self._cost_of_amount += cost

    def add_loss(self, loss: float):
        """
        Consider a loss as a superficial loss and add it to your cost basis.
        :param loss: The positive amount of fiat lost in a trade.
        """
        assert loss > 0
        self._cost_of_amount += loss

    def get_proceeds(self, year: Optional[int] = None):
        if year is None:
            return sum(self._proceeds.values())
        else:
            return self._proceeds[year]

    def get_total_cost_of_amount_sold(self, year: Optional[int] = None):
        if year is None:
            return sum(self._total_cost_of_amount_sold.values())
        else:
            return self._total_cost_of_amount_sold[year]

    def update_cost_of_amount_sold(self, amount: float, date):
        # Update total_cost based on proportion of amount.
        self._total_cost_of_amount_sold[date.year] += amount / self._amount * self._cost_of_amount

    def update_proceeds(self, proceeds_to_add: float, date):
        self._proceeds[date.year] += proceeds_to_add


@singleton
class Portfolio(object):
    @inject
    def __init__(self, config: Configuration,
                 exchanges: Dict[str, TradingExchange],
                 logger: Logger,
                 price_data: PriceData):
        self._logger = logger
        self._exchanges = exchanges
        self._price_data = price_data

        self._asset_map = {
            'ANS': 'NEO',
        }

        self._analysis_config = config.get('analysis') or dict()
        self._fiat = self._analysis_config.get('fiat')
        self._ignore_assets = set(self._analysis_config.get('ignore assets'))
        self._num_transfer_days = self._analysis_config.get('num transfer days') or 1.5

        # Canada has a superficial loss period where losses are complicated to claim
        # if the asset was purchased within some days of the loss.
        # Default to 0 superficial loss days for countries that don't have such rules.
        self._num_superficial_loss_days = self._analysis_config.get('num superficial loss days') or 0

    def _is_fiat(self, symbol):
        return symbol == self._fiat

    def _map_asset(self, asset_name):
        return self._asset_map.get(asset_name, asset_name)

    def analyze(self):
        print("WARNING DISCLAIMER NOTICE: The results and code provided are not meant as tax advice.")
        imports = self._analysis_config.get('import') or []
        data = []
        for i in imports:
            path = os.path.expanduser(i['path'])
            d = pd.read_csv(path,
                            parse_dates=['Date'],
                            )
            data.append(d)

        assert data, "No transactions found."
        data: pd.DataFrame = pd.concat(data)

        if 'Currency.1' in data.columns:
            traded_asset_index = data.columns.get_loc('Currency.1') + 1
        else:
            traded_asset_index = data.columns.get_loc('Sent Currency') + 1

        # Used to be just 'Currency'.
        received_currency_index = data.columns.get_loc('Received Currency') + 1
        # Used to be just 'Quantity'.
        received_quantity_index = data.columns.get_loc('Received Quantity') + 1
        # Used to be just 'Price'.
        sent_quantity_index = data.columns.get_loc('Sent Quantity') + 1

        exchange_index = data.columns.get_loc('Received Wallet Type') + 1

        data.sort_values('Date', inplace=True)
        # Reset the index column.
        data.reset_index(drop=True, inplace=True)

        matched_rows = bidict()

        # TODO Load trades from exchanges based on ones listed in config.

        # Iterate over trades, withdrawals, and fundings to tally:
        # * costs and proceeds
        # * link transfers of similar amounts at close times to not consider them as a trade.
        assets = defaultdict(DigitalAssetHodling)
        losses = []
        prev_year = None
        fiat_values = []
        gains = []
        for row in tqdm(data.itertuples(),
                        desc="Processing actions",
                        total=len(data),
                        unit_scale=True, mininterval=2, unit=" actions"):
            fiat_value = None
            gain = None
            if (isinstance(row.Disabled, (bool, str)) and row.Disabled) or \
                    (self._ignore_assets and (self._map_asset(row[received_currency_index]) in self._ignore_assets or
                                              self._map_asset(row[traded_asset_index]) in self._ignore_assets)):
                self._logger.debug("Skipping row %s.", row)
                fiat_values.append(fiat_value)
                gains.append(gain)
                continue

            if prev_year is not None:
                if row.Date.year != prev_year:
                    self.summarize(assets, losses, prev_year)
            prev_year = row.Date.year

            if row.Type == 'Received':
                asset = row[received_currency_index]
                if self.find_nearby(asset, row, data, matched_rows,
                                    received_quantity_index, sent_quantity_index) is None:
                    amount = row[received_quantity_index]
                    asset_hodlings = assets[self._map_asset(asset)]
                    time_in_s = time.mktime(row.Date.timetuple())
                    try:
                        fiat_value = amount * self._price_data.get_hour_value(asset, self._fiat, time_in_s)
                        # Assume the value paid, if any, is the current price.
                        # E.g. a friend pays you so it's like you took the money to buy the asset.
                        asset_hodlings.add(amount, fiat_value)
                    except:
                        self._logger.exception("Error processing %s.", row)
            elif row.Type == 'Sent':
                asset = row[traded_asset_index]
                if self.find_nearby(asset, row, data, matched_rows,
                                    received_quantity_index, sent_quantity_index) is None:
                    # Consider unmatched sends as payments and realize gain/loss.
                    asset_hodlings = assets[self._map_asset(asset)]
                    amount = row[sent_quantity_index]
                    time_in_s = time.mktime(row.Date.timetuple())
                    asset_value_per_amount = self._price_data.get_hour_value(asset, self._fiat, time_in_s)
                    fiat_value = amount * asset_value_per_amount

                    loss = 0
                    claim_loss_now = True

                    if asset_value_per_amount < asset_hodlings.avg_cost:
                        # Loss found.
                        loss = amount * asset_hodlings.avg_cost - fiat_value
                        losses.append((loss, asset))

                        # Check cases for superficial loss.
                        if self.check_traded(asset, row.Index, data, self._num_superficial_loss_days,
                                             received_currency_index,
                                             after=True):
                            # Was bought after, so cannot claim loss.
                            claim_loss_now = False
                        elif not np.isclose(amount, asset_hodlings.amount, rtol=0.02) \
                                and self.check_traded(asset, row.Index, data,
                                                      self._num_superficial_loss_days,
                                                      received_currency_index,
                                                      after=False):
                            # Was bought too soon before and holdings are still kept, so cannot claim loss.
                            claim_loss_now = False
                    try:
                        if not claim_loss_now and loss > 0:
                            asset_hodlings -= amount

                            # Add loss to ACB.
                            asset_hodlings.add_loss(loss)
                            # Do not update proceeds.
                        else:
                            # Can claim loss/gain.
                            gain = fiat_value - amount * asset_hodlings.avg_cost

                            asset_hodlings.update_cost_of_amount_sold(amount, row.Date)
                            asset_hodlings -= amount
                            asset_hodlings.update_proceeds(fiat_value, row.Date)
                    except:
                        self._logger.exception("Error processing %s.", row)
            elif row.Type in trade_types:
                bought_asset = row[received_currency_index]
                bought_quantity = row[received_quantity_index]
                traded_quantity = row[sent_quantity_index]
                traded_asset = row[traded_asset_index]

                if self._is_fiat(traded_asset):
                    fiat_value = traded_quantity
                elif self._is_fiat(bought_asset):
                    fiat_value = bought_quantity
                else:
                    time_in_s = time.mktime(row.Date.timetuple())
                    fiat_value = traded_quantity * self._price_data.get_hour_value(traded_asset, self._fiat, time_in_s)

                if not self._is_fiat(traded_asset):
                    # Realize gain/loss on traded_asset.
                    loss = 0
                    claim_loss_now = True
                    traded_asset_value_per_amount = fiat_value / traded_quantity
                    traded_asset_hodlings = assets[self._map_asset(traded_asset)]

                    if traded_asset_value_per_amount < traded_asset_hodlings.avg_cost:
                        # Loss found.
                        loss = traded_quantity * traded_asset_hodlings.avg_cost - fiat_value
                        losses.append((loss, traded_asset))

                        # Check cases for superficial loss.
                        if self.check_traded(traded_asset, row.Index, data, self._num_superficial_loss_days,
                                             received_currency_index,
                                             after=True):
                            # Was bought after, so cannot claim loss.
                            claim_loss_now = False
                        elif not np.isclose(traded_quantity, traded_asset_hodlings.amount, rtol=0.02) \
                                and self.check_traded(traded_asset, row.Index, data, self._num_superficial_loss_days,
                                                      received_currency_index,
                                                      after=False):
                            # Was bought too soon before and holdings are still kept, so cannot claim loss.
                            claim_loss_now = False
                    try:
                        if not claim_loss_now and loss > 0:
                            traded_asset_hodlings -= traded_quantity

                            # Add loss to ACB.
                            traded_asset_hodlings.add_loss(loss)
                            # Do not update proceeds.
                        else:
                            # Can claim loss/gain.
                            gain = fiat_value - traded_quantity * traded_asset_hodlings.avg_cost

                            traded_asset_hodlings.update_cost_of_amount_sold(traded_quantity, row.Date)
                            traded_asset_hodlings -= traded_quantity
                            traded_asset_hodlings.update_proceeds(fiat_value, row.Date)
                    except:
                        self._logger.exception("Error processing %s.", row)

                if not self._is_fiat(bought_asset):
                    # Update bought asset info.
                    bought_asset_hodlings = assets[self._map_asset(bought_asset)]
                    bought_asset_hodlings.add(bought_quantity, fiat_value)
            elif row.Type == 'Transfer':
                if not isinstance(row[exchange_index], str):
                    # Should be fiat.
                    asset = self._map_asset(row[received_currency_index])
                    asset_hodlings = assets[asset]
                    asset_hodlings.add(row[received_quantity_index], row[received_quantity_index])
                else:
                    # Ignore since it should already be accounted for.
                    pass
            else:
                raise ValueError(f"Unrecognized row type {row.Type} in {row}.")

            fiat_values.append(fiat_value)
            gains.append(gain)

        export_path = self._analysis_config.get('export path')
        if export_path is not None:
            self._logger.info("Exporting actions to `%s`.", export_path)
            data[f'{self._fiat} Value'] = fiat_values
            data[f'{self._fiat} Gain'] = gains
            data = data[data.Disabled != 'Disabled']
            data.to_csv(export_path,
                        columns=["Date", "Type", "Received Quantity",
                                 "Received Currency", "Received Exchange", "Received Wallet",
                                 "Sent Quantity",
                                 "Sent Currency", "Sent Exchange", "Sent Wallet",
                                 f"{self._fiat} Value",
                                 f"{self._fiat} Gain",
                                 ],
                        index=False)

        self.summarize(assets, losses, prev_year)
        self.summarize(assets, losses, show_all_assets=True)

    def check_traded(self,
                     symbol: str,
                     index: int, data: pd.DataFrame,
                     num_days: float,
                     received_currency_index: int,
                     after: bool = True):
        result = False
        if num_days <= 0:
            return result
        date = data.iloc[index].Date

        while True:
            if after:
                index += 1
                if index >= len(data):
                    break
            else:
                index -= 1
                if index < 0:
                    break

            row = data.iloc[index]
            if np.abs(row.Date - date).seconds / seconds_per_day > self._num_superficial_loss_days:
                break
            if row.Type in trade_types and row[received_currency_index] == symbol:
                result = True
                break

        return result

    def find_nearby(self, symbol: str, row, data: pd.DataFrame, matched_rows: bidict,
                    received_quantity_index: int, sent_quantity_index: int):
        result = None

        result_index = matched_rows.get(row.Index)
        if result_index is not None:
            return data.iloc[result_index]

        if row.Type == 'Received':
            amount = row[received_quantity_index]
            amount_field = 'Sent Quantity'
            currency_field = 'Sent Currency'
            types_to_find = {'Sent', 'Transfer'}
        elif row.Type == 'Sent':
            amount = row[sent_quantity_index]
            amount_field = 'Received Quantity'
            currency_field = 'Received Currency'
            types_to_find = {'Received', 'Transfer'}
        else:
            raise ValueError(f"Unrecognized row type in {row}")

        date = row.Date

        for i in range(row.Index - 1, -1, -1):
            if i in matched_rows or i in matched_rows.inv:
                continue
            found_row = data.iloc[i]
            if (date - found_row.Date).seconds / seconds_per_day > self._num_transfer_days:
                break
            if found_row.Type in types_to_find \
                    and symbol == getattr(found_row, currency_field) \
                    and np.isclose(getattr(found_row, amount_field), amount, rtol=0.05):
                result = found_row
                matched_rows[i] = row.Index
                break

        if result is None:
            for i in range(row.Index + 1, len(data)):
                if i in matched_rows or i in matched_rows.inv:
                    continue
                found_row = data.iloc[i]
                if (found_row.Date - date).seconds / seconds_per_day > self._num_transfer_days:
                    break
                if found_row.Type in types_to_find \
                        and symbol == getattr(found_row, currency_field) \
                        and np.isclose(getattr(found_row, amount_field), amount, rtol=0.05):
                    result = found_row
                    matched_rows[i] = row.Index
                    break

        if result is not None:
            self._logger.debug("For row: %s\nfound  :%s", row, result)
        return result

    def summarize(self, assets: Dict[str, DigitalAssetHodling],
                  losses: List[tuple],
                  year: Optional[int] = None, show_all_assets: bool = False):
        total_proceeds = 0
        total_cost_of_amount_sold = 0

        if year is None:
            print("Summary:")
        else:
            print(f"Summary of {year}:")

        if show_all_assets:
            asset_iter = sorted(assets.items(),
                                key=lambda a: a[1].get_proceeds(year) - a[1].get_total_cost_of_amount_sold(year),
                                reverse=True)
        else:
            asset_iter = assets.items()

        for name, asset_hodlings in asset_iter:
            asset_hodlings: DigitalAssetHodling
            proceeds = asset_hodlings.get_proceeds(year)
            cost_basis = asset_hodlings.get_total_cost_of_amount_sold(year)

            total_proceeds += proceeds
            total_cost_of_amount_sold += cost_basis
            if show_all_assets:
                print(name)
                if year is None:
                    print(f"  Amount: {asset_hodlings.amount}")
                print(f"  Proceeds: {proceeds}")
                print(f"  Cost basis for amount sold: {cost_basis}")
                print(f"  Diff: {proceeds - cost_basis}")
        if show_all_assets:
            print()
        print(f"Total proceeds: {total_proceeds}")
        print(f"Total cost basis for amounts sold: {total_cost_of_amount_sold}")
        print(f"Diff: {total_proceeds - total_cost_of_amount_sold}")
        if year is None:
            total_loss = sum(map(itemgetter(0), losses))
            print(f"Total losses: {total_loss}")


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()
    p: Portfolio = injector.get(Portfolio)
    p.analyze()
