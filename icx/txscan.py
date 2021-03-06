#!/usr/bin/env python3

from typing import Iterable, List, Union
import click

from . import service
from .util import *


FULL_ADDR_LEN=42
SHORT_ADDR_LEN=20
def shorten_address(s: str) -> str:
    return shorten(s, SHORT_ADDR_LEN, Shorten.MIDDLE)

SHORT_VALUE_LEN = 20
def format_value(s: str) -> str:
    return shorten(format_decimals(s, 2), SHORT_VALUE_LEN, Shorten.LEFT)


def dict_get(value: dict, keys: Union[any,list], default = None) -> any:
    if type(keys) is not list:
        keys = [ keys ]
    for k in keys:
        if k in value:
            value = value[k]
        else:
            return default
    return value


class Column:
    def __init__(self, get_value, size: int, format: str = None, name: str = '') -> None:
        self.__get_value = get_value
        self.__size = size
        self.__format = format if format is not None else f'{{:{size}}}'
        self.__name = name

    def get_value(self, *args) -> any:
        return self.__get_value(*args)

    @property
    def size(self):
        return self.__size

    @property
    def format(self):
        return self.__format

    @property
    def name(self):
        return self.__name

TX_COLUMNS = {
    'id': Column(lambda title, tx: tx['txHash'], 66, name='ID'),
    'from': Column(lambda title, tx: dict_get(tx, 'from', '-'), FULL_ADDR_LEN, name='From'),
    'from...': Column(lambda title, tx: shorten_address(dict_get(tx, 'from', '-')), SHORT_ADDR_LEN, name='From'),
    'type': Column(lambda title, tx: dict_get(tx, 'dataType', 'transfer'), 8, name='Type'),
    'method': Column(lambda title, tx: shorten(dict_get(tx, ['data', 'method'], '-'), 20), 20, name='Method'),
    'to': Column(lambda title, tx: dict_get(tx, 'to', '-'), FULL_ADDR_LEN, name='To'),
    'to...': Column(lambda title, tx: shorten_address(dict_get(tx, 'to', '-')), SHORT_ADDR_LEN, name='To'),
    'value': Column(lambda title, tx: format_value(dict_get(tx, 'value', '0')), 20, format='{:>20}', name='Value'),
}
TX_HEIGHT_COLUMN = Column(lambda title, tx: title, 8, format='{:>8}', name='Height')
DEFAULT_COLUMN_NAMES = [ 'id', 'from...', 'type', 'method', 'to', 'value' ]

class RowPrinter:
    def __init__(self, columns: List[Column], file=sys.stdout) -> None:
        formats = []
        seps = []
        names = []
        for column in columns:
            formats.append(column.format)
            seps.append('-'*column.size)
            names.append(column.name)
        self.__columns = columns
        self.__file = file
        self.__format_str = '| ' + ' | '.join(formats) + ' |'
        self.__sep_str = '+-' + '-+-'.join(seps) + '-+'
        self.__header = self.__format_str.format(*names)

    def print_header(self, **kwargs):
        click.secho(self.__header, reverse=True, file=self.__file, **kwargs)

    def print_separater(self, **kwargs):
        click.secho(self.__sep_str, file=self.__file, **kwargs)

    def print_data(self, *args, **kwargs):
        values = []
        for column in self.__columns:
            values.append(column.get_value(*args))
        click.secho(self.__format_str.format(*values), file=self.__file, **kwargs)

def show_txs(printer: RowPrinter, height: int, txs: list, reverse: bool, **kwargs):
    txs = txs.__reversed__() if reverse else txs
    title = str(height)
    for tx in txs:
        printer.print_data(title, tx, **kwargs)
        title = ''

def merge_filters(filter: list):
    def func(tx:dict ) -> bool:
        for f in filter:
            if not f(tx):
                return False
        return True
    return func

def expand_comma(args: Iterable[str]) -> List[str]:
    items = []
    for arg in args:
        for item in arg.split(','):
            items.append(item)
    return items

TC_CLEAR = '\033[K'

@click.command()
@click.argument('block', default="latest")
@click.option('--column', '-c', 'columns', multiple=True)
#@click.argument('columns', nargs=-1)
#@click.option('--block', '--height', 'block', default='latest')
@click.option('--forward', type=bool, is_flag=True, default=False)
@click.option('--nobase', type=bool, is_flag=True, default=False)
@click.option('--to', 'receivers', default=None, multiple=True)
@click.option('--from', 'senders', default=None, multiple=True)
@click.option('--address', '-a', 'addresses', default=None, multiple=True)
@click.option('--method', '-m', 'methods', default=None, multiple=True)
@click.option('--data_type', '-t', 'data_types', default=None, multiple=True)
def scan(columns: List[str], block, forward, nobase, receivers, senders, addresses, methods, data_types):
    """Scanning transactions

    COLUMNS is list of columns to display. Some of following values
    can be used.
    (id, from, from..., type, method, to, to..., value)
    """

    svc = service.get_instance()

    tx_filters = []
    if nobase:
        tx_filters.append(lambda tx: dict_get(tx, 'dataType') != 'base')
    if len(receivers) > 0:
        receivers = expand_comma(receivers)
        receivers = tuple(map(lambda x: ensure_address(x), receivers))
        tx_filters.append(lambda tx: dict_get(tx, 'to') in receivers )
    if len(senders) > 0:
        senders = expand_comma(senders)
        senders = tuple(map(lambda x: ensure_address(x), senders))
        tx_filters.append(lambda tx: dict_get(tx, 'from') in senders )
    if len(addresses) > 0:
        addresses = expand_comma(addresses)
        addresses = tuple(map(lambda x: ensure_address(x), addresses))
        tx_filters.append(lambda tx: dict_get(tx, 'from') in addresses or dict_get(tx,'to') in addresses )
    if len(methods) > 0:
        tx_filters.append(lambda tx: dict_get(tx, ['data', 'method']) in methods)
    if len(data_types) > 0:
        data_types = expand_comma(data_types)
        tx_filters.append(lambda tx: dict_get(tx, 'dataType', 'transfer') in data_types)
    tx_filter = merge_filters(tx_filters)

    if len(columns) == 0:
        columns = DEFAULT_COLUMN_NAMES
    else:
        columns = expand_comma(columns)
    column_data = list(map(lambda x: TX_COLUMNS[x], columns))
    column_data.insert(0, TX_HEIGHT_COLUMN)
    printer = RowPrinter(column_data)

    id = ensure_block(block)
    sep_print = False
    while True:
        print(f'{TC_CLEAR}>Get Block {id}\r', end='')
        blk = svc.get_block(id)
        height = blk['height']
        txs = blk['confirmed_transaction_list']
        txs = list(filter(tx_filter, txs))
        if len(txs) > 0:
            if not sep_print:
                printer.print_header(bold=True)
                sep_print = True
            show_txs(printer, height, txs, not forward)
            #printer.print_separater()
        if forward:
            id = height+1
        else:
            id = height-1