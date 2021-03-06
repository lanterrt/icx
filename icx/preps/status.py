#!/usr/bin/env python

import datetime
import json
from concurrent import futures

import click
from iconsdk.builder.call_builder import CallBuilder

from .. import service
from ..util import CHAIN_SCORE
from . import semanticversion
from .prep import *


class PRep:
    def __init__(self, prep) -> None:
        self.prep = prep
        self.futures = []

@click.command('status')
@click.option('--file', type=str, default=PREPS_JSON)
@click.option('--version', type=str)
def show_status(file: str, version: str):
    #-------------------------------------------------------------------------------
    #   IP정보를 읽어 들인다.
    #
    fd = open(file, "r")
    prep_info = json.load(fd)
    fd.close

    #-------------------------------------------------------------------------------
    #   현재 Term정보
    #
    svc = service.get_instance()
    iiss_info = svc.call(CallBuilder(to=CHAIN_SCORE, method="getIISSInfo").build())
    next_term = int(iiss_info['nextPRepTerm'], 0)

    #-------------------------------------------------------------------------------
    #   현재의 prep정보(등급)을 가지고 있습니다.
    #
    preps = icon_getPReps()['preps']

    #-------------------------------------------------------------------------------
    #   getChain 과 getVersion을 모든 PREP들에게 호출한다.
    #
    now=datetime.datetime.now()
    idx=0
    items=[]
    results=[]
    executor = futures.ThreadPoolExecutor()
    for prep in preps:
        addr = prep['address']
        if 'nodeAddress' in prep:
            addr = prep['nodeAddress']
        if addr not in prep_info:
            if prep['grade'] == '0x1':
                items.append(PRep(None))
                continue
            else:
                item.append(PRep({
                    'name': prep['name'],
                    'type': GRADE_TO_TYPE[prep['grade']],
                    'power': int(prep['power'], 0),
                }))
                continue

        info = prep_info[addr]
        if 'name' not in info or 'ip' not in info:
            items.append(PRep(None))
            continue

        item = PRep({
            'name': prep['name'],
            'ip': info['ip'],
            'type': GRADE_TO_TYPE[prep['grade']],
            'power': int(prep['power'], 0),
        })
        future = executor.submit(node_get_chain, info['ip'])
        results.append(future)
        item.futures.append(future)
        future = executor.submit(node_get_version, info['ip'])
        results.append(future)
        item.futures.append(future)
        items.append(item)
    futures.as_completed(results)

    #-------------------------------------------------------------------------------
    #   최근 버전, 높이를 구한다.
    #

    top_height=0
    last_version=None
    for item in items:
        try:
            item.chain = item.futures[0].result()
            if 'height' in item.chain:
                height = item.chain['height']
                if height > top_height:
                    top_height = height
            item.version = item.futures[1].result()
            if semanticversion.is_lower_version(last_version, item.version):
                last_version = item.version
        except:
            item.chain = None
            item.version = "unknown"

    version_check = last_version
    if version is not None:
        version_check = version

    #-------------------------------------------------------------------------------
    #   화면출력
    #
    GC='\033[2m'
    WC='\033[31;1m'
    IC='\033[32;1m'
    MC='\033[33;1m'
    BC='\033[34;1m'
    NC='\033[0m'
    STATUS_FORMAT=f'[%3d] %-18s (%4s): %-15s '
    NOPOWER_FORMAT=f'{GC}[%3d] %-18s (%4s): %-15s{NC} '
    MAIN_FORMAT=f'{BC}[%3d] %-18s (%4s): %-15s{NC} '
    LAST_FORMAT='>>>  Late: %d / %d'
    LAST_FOOTER="  <<<"
    idx=0
    late_nodes=0
    updated_main=0
    updated_in22=0
    updated_nodes=0
    all_nodes=0
    main_nodes=0
    for item in items:
        if item.prep is None:
            idx += 1
            continue

        args = (idx, item.prep['name'][:18], item.prep['type'], item.prep['ip'])
        has_power = item.prep['power'] > 0
        if has_power:
            if item.prep['type'] == 'Main':
                format = MAIN_FORMAT
            else:
                format = STATUS_FORMAT
        else:
            format = NOPOWER_FORMAT

        if item.chain is None:
            format += ': %s'
            args += (f'{MC}FAIL{NC}',)
        else:
            all_nodes += 1
            if version_check is None:
                format += ': %-7s '
                args += (item.version,)
            elif semanticversion.is_lower_version(item.version, version_check):
                format += f': {WC}%-16s{NC} '
                args += (item.version,)
                if item.prep['type'] == 'Main':
                    main_nodes += 1
            else:
                format += f': {IC}%-16s{NC} '
                args += ('[OK]',)
                updated_nodes+=1
                if item.prep['type'] == 'Main':
                    updated_main += 1
                    main_nodes += 1
                if idx < 22:
                    updated_in22 += 1

            if 'height' in item.chain and 'state' in item.chain:
                height = item.chain['height']
                state = item.chain['state']
                if height < top_height-2:
                    format += f': {WC}%8d %s{NC} (%d)'
                    args += (height, state, height-top_height)
                    late_nodes += 1
                else:
                    format += f': %8d %s'
                    args += (height, state)

        print(format%args)
        idx += 1
    format=LAST_FORMAT
    args=(late_nodes, all_nodes)

    time_next = now + datetime.timedelta(seconds=(next_term-top_height)*2)
    format+='  NextTerm: %d / %s'
    args+=(next_term, str(time_next.strftime('%H:%M:%S')))
    if version_check is not None:
        format+='   %s Updated: %d / %d / %d'
        args+=(version_check, updated_main, updated_nodes, all_nodes)
    format+=LAST_FOOTER
    print(format%args)
