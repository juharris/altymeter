import unittest

from altymeter.api.bittrex import BittrexApi
from altymeter.module.test_module import TestModule


class TestBittrexApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inj = TestModule.get_injector()
        cls.bittrex = cls.inj.get(BittrexApi)
        """ :type: BittrexApi"""

    def test_get_traded_pairs(self):
        pairs = self.bittrex.get_traded_pairs()
        self.assertGreater(len(pairs), 0, "No pairs found.")
        found = False
        coin = "ETH"
        for p in pairs:
            if p.to == coin:
                found = True
                break
        self.assertTrue(found, "Did not find {}.".format(coin))

    def test_get_recent_stats(self):
        stats = self.bittrex.get_recent_stats('ETH-LTC')
        self.assertEqual(stats.name, 'ETH-LTC')
        self.assertGreater(stats.last_price, 0)
