from injector import Injector, Module

from altymeter.module.db_module import TestDbModule
from altymeter.module.module import AltymeterModule


class TestModule(Module):
    _injector = None

    @classmethod
    def get_injector(cls):
        if cls._injector is None:
            cls._injector = Injector([cls,
                                      AltymeterModule,
                                      TestDbModule,
                                      ])
        return cls._injector
