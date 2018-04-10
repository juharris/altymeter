import unittest
from injector import with_injector, inject
from altymeter.module.module import AltymeterModule
from altymeter.trade.trade_cycles import InefficientMarkerFinder


class TestInefficientMarkerFinder(unittest.TestCase):
    @classmethod
    @with_injector(AltymeterModule)
    def setUpClass(cls):
        pass

    @inject
    def test_find_cycles_for(self, t: InefficientMarkerFinder):
        # No cycles to find inefficiencies in.
        edges = dict(
            BTC=['ETH'],
            ETH=['BTC'],
        )
        cycles = t._find_cycles_for('BTC', edges)
        self.assertEqual([], cycles)

        edges = dict(
            BTC=['ETH', 'XRP'],
            ETH=['BTC', 'XRP'],
            XRP=['BTC', 'ETH']
        )
        cycles = t._find_cycles_for('BTC', edges)
        cycles = set(map(tuple, cycles))
        self.assertEqual({('BTC', 'ETH', 'XRP', 'BTC'),
                          ('BTC', 'XRP', 'ETH', 'BTC')},
                         cycles)

        edges = dict(
            BTC=['ETH', 'XRP', 'NEO', 'XMR'],
            ETH=['BTC', 'XRP', 'NEO'],
            XRP=['BTC', 'ETH'],
            NEO=['BTC', 'ETH'],
            XMR=['BTC']
        )
        cycles = t._find_cycles_for('BTC', edges)
        cycles = set(map(tuple, cycles))
        self.assertEqual({('BTC', 'ETH', 'XRP', 'BTC'),
                          ('BTC', 'ETH', 'NEO', 'BTC'),
                          ('BTC', 'XRP', 'ETH', 'BTC'),
                          ('BTC', 'XRP', 'ETH', 'NEO', 'BTC'),
                          ('BTC', 'NEO', 'ETH', 'BTC'),
                          ('BTC', 'NEO', 'ETH', 'XRP', 'BTC')},
                         cycles)

        cycles = t._find_cycles_for('BTC', edges, max_cycle_length=4)
        cycles = set(map(tuple, cycles))
        self.assertEqual({('BTC', 'ETH', 'XRP', 'BTC'),
                          ('BTC', 'ETH', 'NEO', 'BTC'),
                          ('BTC', 'XRP', 'ETH', 'BTC'),
                          ('BTC', 'NEO', 'ETH', 'BTC')},
                         cycles)
