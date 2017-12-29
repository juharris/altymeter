from logging import Logger

import dpath.util
import requests
from injector import inject, singleton

from altymeter.module.constants import Configuration


@singleton
class Ocr(object):
    @inject
    def __init__(self,
                 config: Configuration,
                 logger: Logger
                 ):
        self._logger = logger
        api_config = config.get('API') or {}
        azure_config = api_config.get('Azure') or {}
        cognitive_config = azure_config.get('Cognitive') or {}
        if not cognitive_config:
            self._logger.warning("No API.Azure.Cognitive config found in configuration.")
        self._subscription_key = cognitive_config.get('subscription key')
        self._endpoint_base = '{}/vision/v1.0/ocr'.format(cognitive_config.get('endpoint base'))

    def read(self, pic_url):
        headers = {
            'Content-Type': 'application/json',
            'Ocp-Apim-Subscription-Key': self._subscription_key,
        }

        params = dict(
            language='en',
            detectOrientation='true',
        )

        r = requests.post(self._endpoint_base, params=params,
                          json=dict(url=pic_url), headers=headers)
        r.raise_for_status()
        lines = []
        for line in dpath.util.values(r.json(), 'regions/*/lines/*'):
            globs = dpath.util.values(line, 'words/*/text')
            lines.append(" ".join(globs))
        result = "\n".join(lines)
        return result
