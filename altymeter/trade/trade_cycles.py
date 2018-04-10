import random
from collections import defaultdict
from logging import Logger
from typing import Dict, List

import numpy as np
from injector import inject, singleton
from tqdm import tqdm

from altymeter.api.exchange import TradedPair, TradingExchange
from altymeter.module.constants import Configuration


@singleton
class InefficientMarkerFinder(object):
    @inject
    def __init__(self, config: Configuration,
                 exchanges: Dict[str, TradingExchange],
                 logger: Logger):
        self._logger = logger
        self._exchanges = exchanges

        trading_config = config.get('trading') or {}
        inefficient_market_config = trading_config.get('inefficient market') or {}
        self._max_cycle_length = inefficient_market_config.get('max cycle length', 4)
        self._min_profit = inefficient_market_config.get('min profit', 0.05)
        self._forbidden = set(inefficient_market_config.get('forbidden') or []) or None
        self._required = set(inefficient_market_config.get('required') or []) or None

        allowed_exchanges = inefficient_market_config.get('exchanges')
        if allowed_exchanges:
            allowed_exchanges = set(map(str.lower, allowed_exchanges))
            self._exchanges = {exchange: val for (exchange, val) in self._exchanges.items()
                               if exchange.lower() in allowed_exchanges}

    def _find_cycles_for(self, start: str, edges: Dict[str, List[str]],
                         max_cycle_length=None) -> List[List[str]]:
        result = []
        stack = [(start, [start], {start})]

        while stack:
            node, path, seen = stack.pop()
            to_nodes = edges.get(node)
            if to_nodes is None:
                continue
            for to_node in to_nodes:
                if to_node == start:
                    if len(path) > 2:
                        new_path = list(path)
                        new_path.append(to_node)
                        result.append(new_path)
                elif to_node not in seen and \
                        (max_cycle_length is None or len(path) + 1 < max_cycle_length):
                    new_path = list(path)
                    new_path.append(to_node)
                    new_seen = set(seen)
                    new_seen.add(to_node)
                    stack.append((to_node, new_path, new_seen))

        return result

    def _find_cycles_for_pairs(self, traded_pairs: List[TradedPair]) -> List[List[str]]:
        result = []
        edges = defaultdict(list)
        for tp in traded_pairs:
            edges[tp.base].append(tp.to)
            edges[tp.to].append(tp.base)

        # Sort by most common coins for speed.
        starts = sorted(edges.keys(), key=lambda node: len(edges[node]), reverse=True)
        for start in starts:
            cycles = self._find_cycles_for(start, edges, self._max_cycle_length)
            result.extend(cycles)

            # Remove start from the graph.
            del edges[start]
            for nodes in edges.values():
                try:
                    nodes.remove(start)
                except ValueError:
                    pass
        return result

    def find_cycles(self) -> Dict[TradingExchange, List[List[str]]]:
        result = defaultdict(list)
        for exchange in self._exchanges.values():
            self._logger.info("Finding cycles on %s.", exchange.name)
            try:
                traded_pairs = exchange.get_traded_pairs()
                cycles = self._find_cycles_for_pairs(traded_pairs)
                result[exchange] = cycles
                self._logger.info("Found %d cycles on %s.", len(cycles), exchange.name)
            except:
                self._logger.exception("Error finding cycles on %s.", exchange.name)

        return result

    def trade(self):
        exchange_cycles = self.find_cycles()
        assert exchange_cycles, "No cycles found."
        exchanges = list(exchange_cycles.keys())
        with tqdm(desc="Finding cycles", unit="cycle") as pbar:
            while True:
                try:
                    exchange = random.choice(exchanges)
                    """:type: TradingExchange"""
                    cycle = random.choice(exchange_cycles[exchange])
                    if self._forbidden and self._forbidden.intersection(cycle):
                        continue
                    if self._required and len(self._required.intersection(cycle)) == 0:
                        continue
                    traded_pairs_map = defaultdict(set)
                    traded_pairs = exchange.get_traded_pairs()
                    for tp in traded_pairs:
                        traded_pairs_map[tp.base].add(tp.to)
                    flow = 1
                    skip = False
                    for i in range(len(cycle) - 1):
                        order_type = 'ask'
                        next_price = np.inf
                        base = cycle[i]
                        to = cycle[i + 1]
                        f = min
                        if to not in traded_pairs_map[base]:
                            base, to = to, base
                            order_type = 'bid'
                            next_price = -np.inf
                            f = max
                        orders = exchange.get_order_book(base=base, to=to, order_type=order_type)
                        if len(orders) == 0:
                            skip = True
                            break
                        # TODO Consider a few orders for the price.
                        for order in orders:
                            if order.order_type == order_type:
                                next_price = f(next_price, order.price)
                        if order_type == 'ask':
                            flow /= next_price
                        else:
                            flow *= next_price
                    self._logger.debug("%s: %s: %s", exchange.name, cycle, flow)
                    if not skip and flow >= 1 + self._min_profit:
                        self._logger.info("FOUND cycle on %s: %s: %s", exchange.name, cycle, flow)
                        # TODO Trade.
                    pbar.update()
                except:
                    self._logger.exception("Error finding negative cycles.")


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()
    t = injector.get(InefficientMarkerFinder)
    """ :type: InefficientMarkerFinder """
    t.trade()
