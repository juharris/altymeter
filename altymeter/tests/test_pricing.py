import time
import unittest
from operator import itemgetter

from altymeter.module.test_module import TestModule
from altymeter.pricing import PriceData, SplitPrices, Trade


class TestPriceData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inj = TestModule.get_injector()
        cls.price_data = cls.inj.get(PriceData)

    def test_add_prices(self):
        pair = 'PAIR_test_add_prices'
        prices = [
            Trade(1, 5, 1518214842.0),
            Trade(2, 6, 1518214842.1),
            Trade(3, 7, 1518214842.2),
            Trade(4, 8, 1518214842.3),
        ]
        self.price_data.add_prices(pair, prices)
        self.assertEqual(self.price_data.get_trades(pair), prices)

    def test_add_prices_already_exists(self):
        pair = 'PAIR_test_add_prices_already_exists'
        duplicate_trade = Trade(3, 4, 1518214842.8724)
        prices = [
            duplicate_trade,
        ]
        self.price_data.add_prices(pair, prices)
        self.assertEqual(self.price_data.get_trades(pair), prices)

        # Shouldn't change.
        self.price_data.add_prices(pair, prices)
        self.assertEqual(self.price_data.get_trades(pair), prices)

    def test_add_prices_duplicate_prices(self):
        pair = 'PAIR_dup'
        # Trades at different times.
        duplicate_trade = Trade(3, 4, 1518214842.8724)
        duplicate_trade2 = Trade(3, 4, 1521214842.8724)
        prices = [
            Trade(2, 3, 1508724842.8724),
            Trade(5, 7, 1518204842.8724),
            duplicate_trade,
            duplicate_trade2,
        ]
        self.price_data.add_prices(pair, prices)

        expected = sorted(prices, key=itemgetter(2))
        self.assertEqual(self.price_data.get_trades(pair), expected)

        prices = [
            duplicate_trade,
            duplicate_trade2,
            Trade(4, 3, 1528724842.8724),
            Trade(5, 3, 1538724842.8724),
        ]

        self.price_data.add_prices(pair, prices)

        expected = [
            Trade(2, 3, 1508724842.8724),
            Trade(5, 7, 1518204842.8724),
            duplicate_trade,
            duplicate_trade2,
            Trade(4, 3, 1528724842.8724),
            Trade(5, 3, 1538724842.8724),
        ]
        self.assertEqual(self.price_data.get_trades(pair), expected)

    def test_add_prices_merge_duplicates(self):
        pair = 'PAIR_test_add_prices_merge_duplicates'
        duplicate_trade = Trade(3, 4, 1518214842.8724)
        prices = [
            duplicate_trade,
            duplicate_trade,
        ]
        self.price_data.add_prices(pair, prices)

        expected = [
            Trade(duplicate_trade.price, duplicate_trade.amount * 2, duplicate_trade.time),
        ]
        self.assertEqual(self.price_data.get_trades(pair), expected)

    def test_add_prices_merge_duplicates2(self):
        pair = 'PAIR_test_add_prices_merge_duplicates2'
        duplicate_trade = Trade(3, 4, 1518214842.8724)
        prices = [
            duplicate_trade,
            duplicate_trade,
            duplicate_trade,
            Trade(2, 3, duplicate_trade.time + 1),
            Trade(5, 7, duplicate_trade.time + 2),
        ]
        self.price_data.add_prices(pair, prices)

        expected = [
            Trade(duplicate_trade.price, duplicate_trade.amount * 3, duplicate_trade.time),
            Trade(2, 3, duplicate_trade.time + 1),
            Trade(5, 7, duplicate_trade.time + 2),
        ]
        self.assertEqual(self.price_data.get_trades(pair), expected)

    def test_add_prices_merge_duplicates3(self):
        pair = 'PAIR_test_add_prices_merge_duplicates3'
        duplicate_trade = Trade(3, 4, 1518214842.8724)
        prices = [
            Trade(2, 3, duplicate_trade.time - 2),
            Trade(5, 7, duplicate_trade.time - 1),
            duplicate_trade,
            duplicate_trade,
            duplicate_trade,
        ]
        self.price_data.add_prices(pair, prices)

        expected = [
            Trade(2, 3, duplicate_trade.time - 2),
            Trade(5, 7, duplicate_trade.time - 1),
            Trade(duplicate_trade.price, duplicate_trade.amount * 3, duplicate_trade.time),
        ]
        self.assertEqual(self.price_data.get_trades(pair), expected)

    def test_get_hour_value(self):
        t = 1516414600
        api_val = self.price_data.get_hour_value('XRP', 'CAD', t)
        stored_val = self.price_data.get_hour_value('XRP', 'CAD', t + 60 * 30)
        self.assertEqual(api_val, stored_val)

    def test_get_prices(self):
        pair = 'PAIR'
        prices = [
            Trade(10, 5, 1499900000.2654),
            Trade(10, 5, 1498200000.2654),
            Trade(10, 6, 1498204842.8723),
            Trade(14, 6, 1498204842.8724),
        ]
        self.price_data.add_prices(pair, prices)

        expected = sorted(prices, key=itemgetter(2))

        self.assertEqual(self.price_data.get_trades(pair), expected)

        prices = self.price_data.get_prices(pair)
        expected_prices = SplitPrices([[10.0], [12.0], [10.0]])
        # Comparing strings since they're not always equal due to floating point issues.
        # This may fail is the user configures the time grouping to be very very small.
        self.assertEqual(str(prices), str(expected_prices))

        self.assertIn(pair, self.price_data.get_pairs())

        pair = 'PAIR2'
        prices = [
            Trade(10, 5, 1499900000.2654),
            Trade(10, 5, 1498200000.2654),
            Trade(10, 6, 1498204842.8723),
            Trade(14, 6, 1498204842.8724),
        ]
        self.price_data.add_prices(pair, prices)

        expected = sorted(prices, key=itemgetter(2))

        self.assertEqual(self.price_data.get_trades(pair), expected)

        prices = self.price_data.get_prices(pairs=['PAIR', 'PAIR2'])
        expected_prices = SplitPrices([[10.0], [12.0], [10.0], [10.0], [12.0], [10.0]])
        # Comparing strings since they're not always equal due to floating point issues.
        # This may fail is the user configures the time grouping to be very very small.
        self.assertEqual(str(prices), str(expected_prices))

        self.assertIn('PAIR', self.price_data.get_pairs())
        self.assertIn(pair, self.price_data.get_pairs())

    def test_has_continuous_trades_since(self):
        t = int(time.time())
        pair = 'PAIR_has_trades_since'
        prices = [
            Trade(10, 5, t - self.price_data.time_grouping * 2),
            Trade(10, 5, t - self.price_data.time_grouping * 1),
            Trade(10, 5, t),
        ]
        self.price_data.add_prices(pair, prices)

        since = t - self.price_data.time_grouping * 4
        actual = self.price_data.has_continuous_trades_since(pair, since)
        self.assertFalse(actual, "There should not be data since %s." % since)

        since = t - self.price_data.time_grouping * 3
        actual = self.price_data.has_continuous_trades_since(pair, since)
        self.assertFalse(actual, "There should not be data since %s." % since)

        actual = self.price_data.has_continuous_trades_since(pair, t - self.price_data.time_grouping * 2)
        self.assertTrue(actual)

        actual = self.price_data.has_continuous_trades_since(pair, t - self.price_data.time_grouping * 1)
        self.assertTrue(actual)

        actual = self.price_data.has_continuous_trades_since(pair, t)
        self.assertTrue(actual)
