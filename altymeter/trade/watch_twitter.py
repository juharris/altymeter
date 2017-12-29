import re
from logging import Logger
from typing import Dict

import twitter
from injector import inject
from pushbullet import Pushbullet

from altymeter.api.exchange import TradingExchange
from altymeter.module.constants import Configuration
from altymeter.trade.ocr import Ocr
import dpath.util


class TwitterWatchingTrader(object):
    @inject
    def __init__(self,
                 config: Configuration,
                 logger: Logger,
                 exchanges: Dict[str, TradingExchange],
                 ocr: Ocr):
        self._logger = logger
        self._exchanges = exchanges
        self._ocr = ocr

        pushbullet_api_config = config['API']['Pushbullet']
        self._pushbullet_api = Pushbullet(api_key=pushbullet_api_config['api key'],
                                          encryption_password=pushbullet_api_config['encryption password'])

        devices = self._pushbullet_api.devices
        self._pushbullet_device = None
        for d in devices:
            if d.nickname == pushbullet_api_config['device name']:
                self._pushbullet_device = d
        assert self._pushbullet_device is not None, "Couldn't find Pushbullet device."
        self._numbers_to_notify = pushbullet_api_config.get('numbers to notify') or []

        twitter_api_config = config['API']['Twitter']
        self._twitter_api = twitter.Api(consumer_key=twitter_api_config['consumer key'],
                                        consumer_secret=twitter_api_config['consumer secret'],
                                        access_token_key=twitter_api_config['access token key'],
                                        access_token_secret=twitter_api_config['access token secret'])

        self._config = config

        self._watch_config = twitter_api_config['watch']

    def _is_within_times(self, tweet: dict, start_time_s, end_time_s):
        result = True
        utc_time_of_day_s = (int(tweet['timestamp_ms']) / 1000) % (60 * 60 * 24)
        if (start_time_s is not None and utc_time_of_day_s < start_time_s) or \
                (end_time_s is not None and end_time_s < utc_time_of_day_s):
            result = False
        return result

    def _notify(self, tweet: dict, coin_name: str):
        text = "\"{}\"".format(tweet['text'])
        if coin_name:
            text += "\nhttps://coinmarketcap.com/currencies/{}".format(coin_name)
        self._logger.info("Sending: \"%s\".", text)
        for num in self._numbers_to_notify:
            self._pushbullet_api.push_sms(self._pushbullet_device, num, text)

    def _trade(self, tweet: dict, coin: str):
        is_dry_run = self._config.get('trading', {}).get('dry run', False)
        # Find on an exchange.
        for exchange in self._exchanges.values():
            self._logger.debug("Checking %s.", exchange.name)
            # Determine allowed bases.
            exchange_bases = set(self._config['exchanges'][exchange.name].get('bases') or [])

            try:
                for tp in exchange.get_traded_pairs():
                    if tp.to == coin or tp.to_full_name == coin:
                        if len(exchange_bases) > 0 and tp.base not in exchange_bases:
                            self._logger.debug("Found pair with non permitted base: %s", tp)
                            continue
                        if is_dry_run:
                            self._logger.info("Would buy %s.", tp.name)
                        else:
                            # Buy.
                            try:
                                # Determine volume.
                                recent_stats = exchange.get_recent_stats(pair=tp.name)
                                price = recent_stats.weighted_avg_price or recent_stats.last_price
                                # TODO FIXME Load desired volumes from config.
                                volume = 10
                                if tp.base == "ETH":
                                    volume = 0.8 / price
                                elif tp.base == "BTC":
                                    volume = 0.025 / price

                                # Some exchanges work better with integer volumes.
                                volume = int(volume)
                                # TODO Make price multiplier configurable.
                                price *= 1.5
                                order = exchange.create_order(pair=tp.name,
                                                              action_type='buy',
                                                              order_type='limit',
                                                              price=price,
                                                              volume=volume)

                                # Make sure sell price isn't too low.
                                price = max(order.price, price * 0.9)

                                # TODO Option to make sure that order was successful before selling
                                # so that the user's existing assets aren't sold.

                                # Sell
                                # TODO Load multipliers from config.
                                # Notice that the volume multiplier don't sum to 1: HODL.
                                price_vols = [
                                    (1.4, 0.3),
                                    (1.6, 0.2),
                                    (2, 0.25),
                                    (2.2, 0.2),
                                ]
                                for price_mul, vol_mul in price_vols:
                                    try:
                                        exchange.create_order(pair=tp.name,
                                                              action_type='sell',
                                                              order_type='limit',
                                                              time_in_force='GTC',
                                                              price=price * price_mul,
                                                              volume=int(volume * vol_mul))
                                    except:
                                        self._logger.exception("Error selling {} on {}.".format(
                                            tp.name, exchange.name))
                            except:
                                self._logger.exception("Error exchanging {} on {}.".format(
                                    tp.name, exchange.name))
            except:
                self._logger.exception("Error using {} exchange.".format(exchange.name))

    def watch(self):
        screen_names = set(self._watch_config['screen names'])
        pattern = re.compile(self._watch_config['pattern'], re.IGNORECASE | re.MULTILINE)

        photo_text_pattern = self._watch_config.get('photo text pattern')
        if photo_text_pattern:
            photo_text_pattern = re.compile(photo_text_pattern, re.IGNORECASE | re.MULTILINE)
        start_time_of_day_s = self._watch_config.get('start time of day seconds')
        end_time_of_day_s = self._watch_config.get('end time of day seconds')

        self._logger.info("Waiting for tweets with screen names in: %s"
                          "\npattern: %s"
                          "\nphoto text pattern: %s"
                          "\nstart time of day seconds: %s"
                          "\nend time of day seconds: %s",
                          screen_names, pattern, photo_text_pattern,
                          start_time_of_day_s, end_time_of_day_s)
        user_ids = [str(self._twitter_api.GetUser(screen_name=screen_name).id) for screen_name in screen_names]
        for tweet in self._twitter_api.GetStreamFilter(follow=user_ids):
            if tweet['user']['screen_name'] in screen_names and not tweet['retweeted']:
                text = tweet['text']
                self._logger.debug("Tweet: \"%s\"", text)
                m = pattern.search(text)
                if not m:
                    for media in dpath.util.values(tweet, 'entities/media/*'):
                        if media['type'] == 'photo':
                            photo_url = media['media_url']
                            photo_text = self._ocr.read(photo_url)
                            self._logger.debug("Photo text: \"%s\" at %s.", photo_text, photo_url)

                            m = pattern.search(photo_text)
                            if m:
                                break
                            m = photo_text_pattern.search(photo_text)
                            if m:
                                break
                if m or self._is_within_times(tweet, start_time_of_day_s, end_time_of_day_s):
                    if m:
                        coin_name = m['coin_name']
                        coin = m['coin']
                        if coin is None:
                            # TODO Try to determine coin.
                            coin = coin_name
                    else:
                        coin_name = None
                        coin = None
                    try:
                        self._notify(tweet, coin_name)
                    except:
                        self._logger.exception("Notifying failed.")
                    if coin is not None:
                        try:
                            self._trade(tweet, coin)
                        except:
                            self._logger.exception("Trading failed.")


if __name__ == '__main__':
    from altymeter.module.module import AltymeterModule

    injector = AltymeterModule.get_injector()

    t = injector.get(TwitterWatchingTrader)
    """ :type: TwitterWatchingTrader """

    t.watch()
