#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.mscan.mdb
MetaDB

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2016 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import sys
import os
import re
import json
import signal
import time
import subprocess

from xbake.common.logthis import *
from xbake.mscan import scrapers


class MCMP:
    NOMATCH = 0
    RENAMED = 1
    NOCHG   = 2

rcdata = {'files': {}, 'series': {}}
tdex = {}


def mkey_match(mkid, mkreal):
    """
    Check against MDB for matches
    """
    dxm = rcdata['files'].get(mkid, False)
    if dxm is False:
        return MCMP.NOMATCH
    elif unicode(dxm) == unicode(mkreal):
        return MCMP.NOCHG
    else:
        return MCMP.RENAMED


def series_scrape(xconfig):
    """
    Scrape info for all series in tdex
    """
    cscraper = xconfig.scan['scraper']
    show_count = len(tdex)

    if show_count < 1:
        logthis("No new shows to scrape. Aborting.", loglevel=LL.VERBOSE)
        return 0

    logthis("** Scraping for series info for %s shows" % (show_count), loglevel=LL.INFO)

    # Iterate through tdex and scrape for series info
    for xsea, xsdat in tdex.iteritems():
        # Check if series data already exists
        if rcdata['series'].get(xsea, None):
            logthis("Series already exists in database. Skipping:", suffix=xsdat, loglevel=LL.INFO)
            del(tdex[xsea])
            show_count -= 1
            continue
        # Execute chosen scraper
        tstatus('series_scrape', scraper=cscraper, tdex_id=xsea, tdex_data=xsdat)
        if cscraper == 'tvdb':
            scrapers.tvdb(xsea, tdex)
        elif cscraper == 'mal':
            scrapers.mal(xsea, tdex)
        else:
            failwith(ER.NOTIMPL, "Scraper [%s] not implemented. Unable to continue. Aborting." % (cscraper))

    return show_count


def series_add(sname, ovrx=False):
    """
    Add series to tdex
    """
    snamex = normalize(sname)

    if tdex.has_key(snamex):
        logthis("inc count for series:", suffix=snamex, loglevel=LL.DEBUG)
        tdex[snamex]['count'] += 1
    else:
        logthis("New series found:", suffix=snamex, loglevel=LL.DEBUG)
        tdex[snamex] = {'title': sname, 'count': 1}
        if ovrx:
            if ovrx.has_key('tvdb_id'): tdex[snamex]['tvdb_id'] = ovrx['tvdb_id']
            if ovrx.has_key('mal_id'): tdex[snamex]['mal_id'] = ovrx['mal_id']

    return snamex


def normalize(xname):
    """
    Normalize input string for use as a tdex_id
    """
    nrgx = u'[`\-%&\*@\(\)#:,\/\\;\+=\[\]\{\}\$\<\>]'
    urgx = u'[ ★☆\.\?\!\']'
    return re.sub(urgx, '_', re.sub(nrgx, '', xname)).lower().strip()

def get_tdex():
    return tdex
