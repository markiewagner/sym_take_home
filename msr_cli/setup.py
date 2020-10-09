from setuptools import setup

setup(
    name='msr',
    version='0.1',
    py_modules=['msr'],
    install_requires=[
        'Click',
        'Requests',
        'Tabulate'
    ],
    entry_points='''
        [console_scripts]
        msr=msr:cli
    ''',
)
