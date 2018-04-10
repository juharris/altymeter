import unittest

from injector import inject, with_injector

from altymeter.api.bittrex import BittrexApi
from altymeter.module.test_module import TestModule


class TestBittrexApi(unittest.TestCase):
    @classmethod
    @with_injector(TestModule)
    def setUpClass(cls):
        pass

    @inject
    def test_get_order_book(self, bittrex: BittrexApi):
        orders = bittrex.get_order_book(base='BTC', to='ETH')
        self.assertGreater(len(orders), 0)
        order_types = set()
        for order in orders:
            order_types.add(order.order_type)
            if len(order_types) == 2:
                break

        self.assertSetEqual({'bid', 'ask'}, order_types)

    @inject
    def test_get_recent_stats(self, bittrex: BittrexApi):
        stats = bittrex.get_recent_stats('ETH-LTC')
        self.assertEqual('ETH-LTC', stats.name)
        self.assertGreater(stats.last_price, 0)

    @inject
    def test_get_traded_pairs(self, bittrex: BittrexApi):
        pairs = bittrex.get_traded_pairs()
        self.assertGreater(len(pairs), 0, "No pairs found.")
        found = False
        coin = "ETH"
        for p in pairs:
            if p.to == coin:
                found = True
                break
        self.assertTrue(found, "Did not find {}.".format(coin))
