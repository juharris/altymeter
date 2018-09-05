import os
import time
from enum import Enum
from logging import Logger
from typing import Iterable, Optional

import numpy as np
import pandas as pd
from bokeh.io import output_file as set_plot_output_file, show as show_plot
from bokeh.layouts import gridplot
from bokeh.models import HoverTool
from bokeh.plotting import figure
from injector import inject
from keras import losses
from keras import optimizers
from keras.activations import softmax
from keras.callbacks import EarlyStopping, ModelCheckpoint, TensorBoard
from keras.layers import Activation, Bidirectional, Dense, Dropout, LSTM
from keras.layers import Conv1D, Flatten
from keras.models import Sequential
from keras.models import load_model
from tqdm import tqdm

from altymeter.module.constants import Configuration, user_dir
from altymeter.pricing import PriceData

ALL_FEATURES = {
    'price',
    'volume',
}
DEFAULT_FEATURES = ALL_FEATURES


class TradeDecision(Enum):
    BUY = 0
    HODL = 1
    """ Hold. The name is not a typo.
    """
    SELL = 2


class TradingModel(object):
    @inject
    def __init__(self, config: Configuration,
                 logger: Logger,
                 price_data: PriceData):
        self._logger = logger
        self._price_data = price_data

        training_config = config.get('training', {})

        self._save_path = training_config.get('save path')
        if self._save_path is not None:
            self._save_path = os.path.expanduser(self._save_path)
            if not os.path.isabs(self._save_path):
                self._save_path = os.path.join(user_dir, self._save_path)
                self._logger.info("Set model save path to `%s`.", self._save_path)

        self._model_type = training_config.get('model type', 'conv').lower()

        # Number of steps to look backward for training data.
        self._num_lookback_steps = training_config.get('num lookback steps')
        if self._num_lookback_steps is None:
            # Default to look back 4 hours.
            self._num_lookback_steps = int(4 * 60 * 60 / self._price_data.time_grouping)
        self._logger.info("Number of look back steps: %d", self._num_lookback_steps)

        # Number of steps to look forward when setting expected value.
        self._num_lookahead_steps = training_config.get('num lookahead steps')
        if self._num_lookahead_steps is None:
            # Default to lookahead 2 hours.
            self._num_lookahead_steps = int(2 * 60 * 60 / self._price_data.time_grouping)

        # Thresholds for deciding if change or neutral flag.
        self._increase_threshold = training_config.get('increase threshold', 0.01)
        self._decrease_threshold = training_config.get('decrease threshold', 0.01)
        self._decision_threshold = training_config.get('decision threshold', 0)
        self._epochs = training_config.get('epochs', 10)
        self._batch_size = training_config.get('batch size', 32)
        self._is_data_plottable = training_config.get('plot data', False)
        self._log_dir = os.path.join(os.path.dirname(__file__), 'log_dirs/%d' % int(time.time()))
        os.makedirs(self._log_dir)

        self._features = set(training_config.get('features', DEFAULT_FEATURES))
        assert len(self._features - ALL_FEATURES) == 0, "Extra features given: %s" % (self._features - ALL_FEATURES)
        self._num_features = len(self._features)
        self._model = None

        self._decision_mapping = {}
        for decision in TradeDecision:
            self._decision_mapping[decision.value] = decision

    def backtest(self, validation_data, market_values,
                 a_count=10 ** 6, b_count=10 ** 6,
                 spend_amount=10 ** 4):
        X_val, y_val = validation_data

        market_value = market_values[0]
        initial_value = a_count * market_value + b_count
        print("Initial:")
        print("A: %s" % a_count)
        print("B: %s" % b_count)
        print("Market value: %f" % market_value)
        print("Total initial value: %.2fB" % initial_value)

        predictions = self._model.predict(X_val)

        for i, prediction in enumerate(predictions):
            # TODO Average market value over a few trades.
            market_value = market_values[i]
            score = max(prediction)
            decision = self.interpret_decision(prediction)
            if decision == TradeDecision.BUY:
                cost = market_value * spend_amount * score
                if b_count > cost:
                    a_count += spend_amount * score
                    b_count -= cost
            elif decision == TradeDecision.SELL:
                # Sell
                cost = spend_amount * score
                if a_count > cost:
                    a_count -= cost
                    b_count += market_value * spend_amount * score
            else:
                # Hold
                pass

        print("Final:")
        print("A: %s" % a_count)
        print("B: %s" % b_count)
        print("Market value: %f" % market_value)
        final_value = a_count * market_value + b_count
        percent_profit = final_value / initial_value
        sign = '+' if percent_profit >= 1 else ''
        print("Final value: %.2fB (%s%0.2f%%)" % (final_value, sign, (percent_profit - 1) * 100))

    def build_training_data(self, pairs: Iterable[str] = None,
                            validation_split=0.,
                            last: Optional[int] = None,
                            is_data_plottable: Optional[bool] = None):
        if is_data_plottable is None:
            is_data_plottable = self._is_data_plottable

        split_prices = self._price_data.get_prices(pairs)

        num_chunks = 0
        data_len = 0
        for split_index, prices in enumerate(split_prices):
            if self._num_lookback_steps + self._num_lookahead_steps + 1 <= len(prices):
                num_chunks += 1
                data_len += len(prices) - self._num_lookback_steps - self._num_lookahead_steps

        assert data_len > 0, "Not enough data to train with. Only %d merged prices in %d chunks." % \
                             (len(split_prices), split_prices.get_num_chunks())

        X, y = [], []
        X_val, y_val = [], []
        validation_market_values = []

        self._logger.debug("Using %d chunk(s).", num_chunks)

        if is_data_plottable:
            plots = []
            path = os.path.join(self._log_dir, 'training_data.html')
            self._logger.info("Saving training data plot to `%s`.", path)
            set_plot_output_file(path, title="Training Data")

        for split_index, prices in tqdm(enumerate(split_prices),
                                        desc="Aggregating trades",
                                        unit_scale=True, mininterval=2, unit=" periods"):
            if len(prices) < self._num_lookback_steps + self._num_lookahead_steps + 1:
                # Can't train with this chunk.
                continue

            volumes = split_prices.volumes[split_index]
            avg_volume = np.mean(volumes)

            chunk_validation_len = int(len(prices) * validation_split)
            chunk_training_data_len = len(prices) - chunk_validation_len
            if chunk_training_data_len < self._num_lookback_steps + self._num_lookahead_steps \
                    or chunk_validation_len < self._num_lookback_steps + self._num_lookahead_steps:
                # Can't do validation with this chunk.
                chunk_validation_len = 0
                chunk_training_data_len = len(prices)

            if is_data_plottable:
                plot_data = []
                price_increase_data = []
                price_decrease_data = []

                for index in range(self._num_lookback_steps):
                    plot_data.append(dict(price=prices[index],
                                          time=index))
            for index in range(self._num_lookback_steps, len(prices) - self._num_lookahead_steps):
                # Subtract 1 since data gets scaled.
                training_datum = np.zeros((self._num_lookback_steps - 1, self._num_features), dtype=np.float32)

                if 'price' in self._features:
                    # Prices have too much variation and are not relative.
                    # So divide price by previous price to get more consistent and learnable data.
                    # Also works instead of normalizing so that we can train and use other pairs with the same model.
                    prices_datum = prices[index - self._num_lookback_steps:index]
                    for price_index in range(len(prices_datum) - 1):
                        # Scale so that we're not working with numbers that are too small.
                        # This actually did improve performance.
                        training_datum[price_index, 0] = 100 * (
                                prices_datum[price_index + 1] / prices_datum[price_index] - 1)

                if 'volume' in self._features:
                    volumes_datum = volumes[index - self._num_lookback_steps:index]
                    for i in range(len(volumes_datum) - 1):
                        training_datum[i, 1] = volumes_datum[i + 1] / avg_volume

                expected_price = np.mean(prices[index:index + self._num_lookahead_steps])
                diff = expected_price / prices[index - 1] - 1

                expected = np.zeros(len(TradeDecision), dtype=np.float32)
                if diff >= self._increase_threshold:
                    expected[TradeDecision.BUY.value] = 1
                    if is_data_plottable:
                        price_increase_data.append(dict(price=prices[index],
                                                        time=index))
                elif diff <= -self._decrease_threshold:
                    expected[TradeDecision.SELL.value] = 1
                    if is_data_plottable:
                        price_decrease_data.append(dict(price=prices[index],
                                                        time=index))
                else:
                    expected[TradeDecision.HODL.value] = 1

                if index < chunk_training_data_len:
                    X.append(training_datum)
                    y.append(expected)
                else:
                    X_val.append(training_datum)
                    y_val.append(expected)
                    validation_market_values.append(prices[index])

                if is_data_plottable:
                    plot_data.append(dict(price=prices[index],
                                          volume=volumes[index],
                                          time=index))

            if is_data_plottable:
                # Data that we can't train with because we can't see ahead of it.
                # Add this data to plots so that the labelling before it makes sense.
                for index in range(len(prices) - self._num_lookahead_steps, len(prices)):
                    plot_data.append(dict(price=prices[index],
                                          time=index))

                plot_data = pd.DataFrame(plot_data)
                # TODO Offset the times by the actual start time and pass: x_axis_type='datetime'.
                plot = figure()
                hover_tool = HoverTool(tooltips=[
                    ("index", "$x"),
                    ("price", "$y"),
                ])
                plot.add_tools(hover_tool)
                plot.line(x='time', y='price', source=plot_data, color='black')
                if price_increase_data:
                    plot.circle(x='time', y='price', source=pd.DataFrame(price_increase_data),
                                size=3, color='green')
                if price_decrease_data:
                    plot.circle(x='time', y='price', source=pd.DataFrame(price_decrease_data),
                                size=3, color='red')

                # TODO Plot volumes.
                # plot.rect(x='time', y='volume', source=plot_data,
                #           width = 1, height='volume')

                plots.append(plot)

        if is_data_plottable:
            grid = gridplot(plots, ncols=2)
            show_plot(grid)

        # TODO Check option to predict sequence.


        # TODO Optimize getting the last values by not accumulating above.
        if last is not None:
            X = X[-last:]
            y = y[-last:]
            X_val = X_val[-last:]
            y_val = y_val[-last:]
            validation_market_values = validation_market_values[-last:]

        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.float32)
        X_val = np.array(X_val, dtype=np.float32)
        y_val = np.array(y_val, dtype=np.float32)

        return X, y, (X_val, y_val), validation_market_values

    def interpret_decision(self, prediction: np.ndarray):
        argmax = prediction.argmax()
        score = prediction[argmax]
        if score > self._decision_threshold:
            result = self._decision_mapping[argmax]
        else:
            result = TradeDecision.HODL
        return result

    def load(self, path):
        self._logger.info("Loading model from `%s`.", path)
        return load_model(path)

    @property
    def num_look_back_steps(self):
        return self._num_lookback_steps

    def train(self, pairs: Iterable[str] = None,
              validation_split=0.3,
              load_path=None):

        X, y, validation_data, validation_market_values = self.build_training_data(pairs, validation_split)

        if load_path:
            self._model = self.load(load_path)
        elif self._model is None:
            self._model = Sequential()
            if self._model_type in ['conv', 'convolutional']:
                self._model.add(Conv1D(filters=1,
                                       kernel_size=4,
                                       # TODO Try with strides=1,
                                       strides=4,
                                       padding='causal',
                                       input_shape=(X.shape[1], X.shape[2])))
                self._model.add(Flatten())
                self._model.add(Dropout(0.1))
            elif self._model_type == 'lstm':
                self._model.add(Bidirectional(LSTM(2 ** int(np.ceil(np.log2(self._num_lookback_steps))),
                                                   dropout=0.5,
                                                   recurrent_dropout=0.5,
                                                   ),
                                              input_shape=(X.shape[1], X.shape[2])))
                self._model.add(Dropout(0.5))
                # TODO Try adding conv after LSTM.
            else:
                raise Exception("Unrecognized model type: `%s`." % self._model_type)
            self._model.add(Dense(y.shape[1]))
            self._model.add(Activation(softmax))

        optimizer = optimizers.SGD()
        self._model.compile(loss=losses.categorical_crossentropy,
                            optimizer=optimizer,
                            metrics=['accuracy'])

        self._model.summary()

        callbacks = [
            EarlyStopping(monitor='val_loss',
                          min_delta=0.01, patience=5,
                          verbose=1),
        ]
        self._logger.info("TensorBoard dir: `%s`.", self._log_dir)
        callbacks.append(TensorBoard(log_dir=self._log_dir,
                                     histogram_freq=1,
                                     ))

        if self._save_path:
            callbacks.append(ModelCheckpoint(self._save_path,
                                             verbose=1,
                                             save_best_only=True))

        class_weights = {
            TradeDecision.BUY.value: 0.3,
            TradeDecision.HODL.value: 0.1,
            TradeDecision.SELL.value: 0.3,
        }

        if len(validation_data[0]) == 0:
            validation_data = None

        # TODO Use fit_generator.
        self._model.fit(X, y,
                        class_weight=class_weights,
                        callbacks=callbacks,
                        verbose=1,
                        batch_size=self._batch_size, epochs=self._epochs,
                        validation_data=validation_data)

        if validation_data and validation_market_values:
            # TODO Backtest on each pair separately.
            self.backtest(validation_data, validation_market_values)

        return self._model


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()
    m = injector.get(TradingModel)

    m.train()
