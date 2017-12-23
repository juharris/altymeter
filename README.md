# Altymeter

Determine if a crypto currency's price will change.

## Development Notes

This has been made public early to share with a friend. Code and package names may change in a backwards incompatible way.

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

There are sensible defaults for all fields except for the API keys.

```
exchanges: # API keys to use exchanges.
log level: # The desired log level (defaults to INFO).
pricing: # Parameters for pricing.
  time grouping: # How to group seconds for training and classifying. Default: group 10 minutes together.
DB connection: # The database connection string (defaults to a file).
test DB connection: # The database connection string for tests (defaults to a file).
training: # Training configuration.
  epochs: # The number of epochs.
  plot data: # `true` if you want to plot helpful data and enable TensorBoard, `false` otherwise.
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
