from distutils.core import setup

from setuptools import find_packages

install_requires = [
    'bokeh>=0.12.6',
    'Django>=1.11.6',
    'dpath>=1.4',
    'injector>=0.13.0',
    'Keras>=2.0.8',
    'numpy',
    'pandas>=0.20',
    'pushbullet.py>=0.11',
    'python-binance>=0.5.6',
    'python-twitter>=3.3',
    'PyYAML',
    'requests',
    'tqdm>=4.19',
]

tests_require = [
    'nose',
]

setup(
    name='altymeter',
    version='0.2.0',
    packages=find_packages(),
    url='',
    license='MIT',
    author='Justin Harris',
    author_email='',
    description='Train models using cryptocurrency data.',
    install_requires=install_requires,
    tests_require=tests_require,
    test_suite="nose.collector",
)
