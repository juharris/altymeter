# Altymeter

Determine if a crypto currency's price will change.

## Development Notes

This has been made public early to share with a friend. Code and package names may change in a backwards incompatible way.

## Supported Exchanges
|Site|Notes|
|---|---|
| Binance | Somewhat supported. |
| Bittrex | Somewhat supported. |
| Kraken | Mainly used. |

## Requirements
1. [Kraken API keys][kraken_api]: to get trading history
2. [Keras][keras]: to train classifiers
3. `python setup.py install`
4. Place your API keys in `~/.altymeter/config.yaml`.
There is an example in this folder.
A default configuration will be created if you do not have one.
You can run `python -c "import os;print(os.path.expanduser('~/.altymeter/config.yaml'))"` to find out where to copy the example to.


by Justin Harris ([github.com/juharris][github])

[github]: http://github.com/juharris
[keras]: https://keras.io
[kraken_api]: https://www.kraken.com/en-us/help/api

## Configuration

The following describes the main keys for configuration. There are many more that are just not documented yet.

There are sensible defaults for *most* fields except for the API keys.

```
API:
  Azure:
    Cognitive: # For reading text in tweeted pictures.
      subscription key: Your subscription key for Azure API's.
      endpoint base: The endpoint for Azure cognitive API's.
  Pushbullet:
    api key:
    device name:
    encryption password:
    numbers to notify: # List of phone numbers to SMS.
  Twitter: # For watching tweets.
    access token key:
    access token secret:
    consumer key:
    consumer secret:
    watch: # For watching specific tweets from users.
      screen names: # Twitter usernames to follow.
        - crazycointweeter
      pattern: 'BUY (?P<coin_name>\w+)(\W*\((?P<coin>\w+)\))?'
      photo text pattern: 'BUY (?P<coin_name>\w+)(\W*\((?P<coin>\w+)\))?'
exchanges: # API keys to use exchanges.
  Binance: # See https://www.binance.com/userCenter/createApi.html to get an API key.
    api key:
    api secret:
  Bittrex: # See https://bittrex.com/Manage#sectionApi to get an API key.
    api key:
    api secret:
  Kraken: # See https://www.kraken.com/en-us/help/api to get an API key.
    api key:
    api secret:
log level: # The desired log level (defaults to INFO).
pricing: # Parameters for pricing.
  time grouping: # How to group seconds for training and classifying. Default: group 10 minutes together.
DB connection: # The database connection string (defaults to a file).
test DB connection: # The database connection string for tests (defaults to a file).
trading: # Configuration for trading.
  dry run: # If trades should not be done and instead just logged.
training: # Training configuration.
  epochs: # The number of epochs.
  plot data: # `true` if you want to plot helpful data and enable TensorBoard, `false` otherwise.
```

## Watching Twitter
Fill in the required configuration values for Twitter and run:
```bash
python altymeter/trade/watch_twitter.py
```

## Starting the UI
Run:
```bash
cd altymeter/altymetersite
python manage.py runserver
```

Then open `http://localhost:8000`.

## License
See [LICENSE.txt](LICENSE.txt).

Dependencies may have other licenses.
