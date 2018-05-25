import logging
import os
import sqlite3

from injector import Module, provider, singleton

from altymeter.module.constants import Configuration, user_dir


class DbModule(Module):
    def __init__(self):
        self._db_initialized = False

    def _initialize_db(self, db: sqlite3.Connection):
        cursor = db.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS trade ('
                       'pair TEXT, price REAL, amount REAL, time REAL,'
                       'UNIQUE (pair, price, amount, time)'
                       ')')
        cursor.execute('CREATE INDEX IF NOT EXISTS trade_index ON trade ('
                       'pair, time ASC'
                       ')')

        cursor.execute('CREATE TABLE IF NOT EXISTS hour_price ('
                       'symbol TEXT, fiat TEXT, time_in_s INTEGER, val REAL,'
                       'UNIQUE (symbol, fiat, time_in_s, val)'
                       ')')
        cursor.execute('CREATE INDEX IF NOT EXISTS hour_price_index ON hour_price ('
                       'symbol, fiat, time_in_s'
                       ')')
        db.commit()

    def _get_database(self, config):
        result = config.get('DB connection')
        if result is None:
            result = os.path.join(user_dir, 'altymeter.db')
        else:
            result = os.path.expanduser(result)
        return result

    @provider
    @singleton
    def provide_db_connection(self, config: Configuration, logger: logging.Logger) -> sqlite3.Connection:
        database = self._get_database(config)
        logger.debug("Database: %s", database)
        result = sqlite3.connect(database, check_same_thread=False)
        if not self._db_initialized:
            self._initialize_db(result)
            self._db_initialized = True
        return result


class TestDbModule(DbModule):
    def __init__(self):
        super().__init__()

    @provider
    @singleton
    def provide_db_connection(self, config: Configuration, logger: logging.Logger) -> sqlite3.Connection:
        database = config.get('test DB connection')
        if database is None:
            database = os.path.join(user_dir, 'test.db')
        else:
            database = os.path.expanduser(database)
        logger.debug("Database: %s", database)

        # Start with a fresh database.
        if not self._db_initialized and os.path.exists(database):
            if database != self._get_database(config):
                os.remove(database)
            else:
                logger.warning("The test database and regular database are the same: `%s`.\n"
                               "It will not be cleared before testing.\n"
                               "This may cause problems if you already have data in the database.", database)

        result = sqlite3.connect(database)
        if not self._db_initialized:
            self._initialize_db(result)
            self._db_initialized = True
        return result
