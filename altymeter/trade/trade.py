import logging
import os
import time
from datetime import datetime
from logging import Logger
from typing import Optional

import pandas as pd
from bokeh.io import output_file as set_plot_output_file, save as save_plot, show as show_plot
from bokeh.models import HoverTool
from bokeh.plotting import figure
from injector import inject

from altymeter.api.exchange import TradingExchange
from altymeter.model.train import TradeDecision, TradingModel
from altymeter.module.constants import Configuration, user_dir
from altymeter.pricing import PriceData


class Trader(object):
    @inject
    def __init__(self,
                 config: Configuration,
                 logger: Logger,
                 price_data: PriceData,
                 trading_exchange: TradingExchange,
                 trainer: TradingModel):
        self._logger = logger
        self._price_data = price_data
        self._trading_exchange = trading_exchange
        self._trainer = trainer

        trading_config = config.get('trading', {})

        self._dry_run = trading_config.get('dry run', False)

        self._model_path = trading_config.get('model path')
        if self._model_path is not None:
            self._model_path = os.path.expanduser(self._model_path)

        self._is_data_plottable = trading_config.get('plot data', False)
        if self._is_data_plottable:
            self._log_dir = os.path.join(user_dir, 'log_dirs/trading/%d' % int(time.time()))
            os.makedirs(self._log_dir)

        self._price_multiplier = trading_config.get('price multiplier', 1.0)

        # TODO Pass a param when training.
        self._trainer._is_data_plottable = self._is_data_plottable

    def trade(self, pair: str, since: Optional[int] = None):
        """
        :param pair:
        :param since: In nanoseconds.
        """

        retrain = self._model_path is None
        purchase_volume_base = 0.1
        trade_interval_time = 5 * 60
        actions = []
        buy_actions = []
        sell_actions = []
        hodl_actions = []

        start_time = time.time()

        # Get enough data to show initial classifying data.
        market_trades_start = int(start_time) - self._price_data.time_grouping * self._trainer.num_look_back_steps

        model = None
        if not retrain:
            model = self._trainer.load(self._model_path)

        if self._is_data_plottable:
            path = os.path.join(self._log_dir, 'trading.html')
            self._logger.info("Saving trade plots to `%s`.", path)
            set_plot_output_file(path, title="{} Trading Data".format(pair))

        plot_shown = False

        # TODO Use API to get more past data so that trading can start.

        while True:
            if retrain:
                try:
                    model = self._trainer.train(validation_split=0.)
                except:
                    self._logger.exception("Error Training.")

            if model is None:
                # There was an error training. Try again next time.
                continue

            # Make sure that there are enough recent prices.
            need_trades_start = int(time.time()) - self._price_data.time_grouping * self._trainer.num_look_back_steps
            # Subtract 2 minutes just to be safe.
            need_trades_start -= 2 * 60
            if not self._price_data.has_continuous_trades_since(pair, need_trades_start):
                # TODO Show when automated trading can start
                # by checking how much time of recent continuous trades exists.
                self._logger.info("Waiting for more data. Need trades since %s.", time.ctime(need_trades_start))
                # It's possible that we just need more data from the last time group so
                time.sleep(trade_interval_time / 2)
                continue

            try:
                prices, _, _, _ = self._trainer.build_training_data([pair], last=1, is_data_plottable=False)
                prediction = model.predict(prices)[0]
                score = max(prediction)
                decision = self._trainer.interpret_decision(prediction)

                self._logger.info("%s: prediction: %s", decision, prediction)
                volume = purchase_volume_base * score
                t = time.strftime('%b %d %Y %X %z')

                # XXX Optimize to only get newest data.
                market_trades = self._price_data.get_trades(pair, since=market_trades_start)

                price = market_trades[-1].price
                price *= self._price_multiplier

                if decision == TradeDecision.BUY:
                    r = self._trading_exchange.create_order(pair=pair,
                                                            type='buy',
                                                            order_type='limit',
                                                            price='{:.8f}'.format(price),
                                                            volume=purchase_volume_base * score,
                                                            validate=self._dry_run,
                                                            expire_time_s=str(int(
                                                                time.time() + (trade_interval_time / 2))))
                    self._logger.info("Result: %s", r)
                    actions.append((t, decision.name, volume, prediction))
                    buy_actions.append(dict(time=datetime.fromtimestamp(time.time()),
                                            price=price))
                elif decision == TradeDecision.SELL:
                    r = self._trading_exchange.create_order(pair=pair,
                                                            type='sell',
                                                            order_type='limit',
                                                            price='{:.8f}'.format(price),
                                                            volume=purchase_volume_base * score,
                                                            validate=self._dry_run,
                                                            expire_time_s=str(int(
                                                                time.time() + (trade_interval_time / 2))))
                    self._logger.info("Result: %s", r)
                    actions.append((t, decision.name, volume, prediction))
                    sell_actions.append(dict(time=datetime.fromtimestamp(time.time()),
                                             price=price))
                else:
                    actions.append((t, decision.name, prediction))
                    hodl_actions.append(dict(time=datetime.fromtimestamp(time.time()),
                                             price=price))
                if self._logger.isEnabledFor(logging.INFO):
                    actions_str = "\n".join(map(str, actions))
                    self._logger.info("Actions:\n%s", actions_str)
            except:
                self._logger.exception("Error Trading.")
                continue

            if self._is_data_plottable:
                plot_data = []
                for market_trade in market_trades:
                    plot_data.append(dict(time=datetime.fromtimestamp(market_trade.time),
                                          price=market_trade.price))

                plot = figure(x_axis_type='datetime')
                # TODO Show actual date.
                # TODO Show decimal number formatted as '{:.8f}'.
                hover_tool = HoverTool(tooltips=[
                    ("time", "$x"),
                    ("price", "$y"),
                ])
                plot.add_tools(hover_tool)

                self._logger.debug("Plotting %d trades.", len(plot_data))
                plot.line(x='time', y='price', source=pd.DataFrame(plot_data), color='black')

                # TODO Highlight orders that went through, maybe make them bigger or change the shape?

                if buy_actions:
                    plot.circle(x='time', y='price', source=pd.DataFrame(buy_actions),
                                size=3, color='green')
                if sell_actions:
                    plot.circle(x='time', y='price', source=pd.DataFrame(sell_actions),
                                size=3, color='red')
                if hodl_actions:
                    plot.circle(x='time', y='price', source=pd.DataFrame(hodl_actions),
                                size=2, color='blue')
                if not plot_shown:
                    show_plot(plot)
                    plot_shown = True
                else:
                    save_plot(plot)

            time.sleep(trade_interval_time)


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()
    t = injector.get(Trader)
    """ :type: Trader """
    t.trade(pair='XETHXXBT')
