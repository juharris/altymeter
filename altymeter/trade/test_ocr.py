import unittest

from injector import inject, with_injector

from altymeter.module.module import AltymeterModule
from altymeter.trade.ocr import Ocr


class TestOcr(unittest.TestCase):
    @classmethod
    @with_injector(AltymeterModule)
    def setUpClass(cls):
        pass

    @inject
    def test_read(self, ocr: Ocr):
        text = ocr.read(
            'https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/Atomist_quote_from_Democritus.png/338px-Atomist_quote_from_Democritus.png')
        self.assertEqual("NOTHING\nEXISTS\nEXCEPT\nATOMS\nAND EMPTY\nSPACE.\nEverything else\nis opinion.", text)
