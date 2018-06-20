import json
import threading
from logging import Logger

from django.http import JsonResponse, HttpResponseNotAllowed
from django.shortcuts import render

from altymeter.api.exchange import TradingExchange
from altymeter.module.module import AltymeterModule

_collection_threads = dict()


def _get_thread_name(exchange, pair):
    return f"collect_{exchange.name}_{pair}"


def collect(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    result = dict()

    params = json.loads(request.body)
    pair = params.get('pair')
    result['pair'] = pair

    inj = AltymeterModule.get_injector()
    exchange: TradingExchange = inj.get(TradingExchange)

    thread_name = _get_thread_name(exchange, pair)

    if thread_name not in _collection_threads:
        # TODO Make sure the pair is allowed on that exchange.
        stop_event = threading.Event()
        thread = threading.Thread(target=lambda: exchange.collect_data(pair, stop_event=stop_event),
                                  name=thread_name)
        thread.start()
        _collection_threads[thread_name] = dict(thread=thread,
                                                stop_event=stop_event)

    return JsonResponse(result)


def get_pairs(request):
    result = dict()

    inj = AltymeterModule.get_injector()
    exchange: TradingExchange = inj.get(TradingExchange)
    traded_pairs = exchange.get_traded_pairs()
    result['tradedPairs'] = list(map(lambda p: p._asdict(), traded_pairs))

    return JsonResponse(result)


def stop_collection(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    result = dict()

    params = json.loads(request.body)
    pair = params.get('pair')
    result['pair'] = pair

    inj = AltymeterModule.get_injector()
    exchange = inj.get(TradingExchange)
    """:type: TradingExchange"""

    logger = inj.get(Logger)
    """:type: Logger"""

    thread_name = _get_thread_name(exchange, pair)

    collection_thread = _collection_threads.get(thread_name)
    if collection_thread:
        logger.info("Stopping thread: %s", thread_name)
        collection_thread['stop_event'].set()
        collection_thread['thread'].join()
        del _collection_threads[thread_name]

    return JsonResponse(result)


def home(request):
    return render(request, 'home.html')
