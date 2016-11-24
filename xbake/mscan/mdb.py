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

from xbake.common.logthis import *
from xbake.mscan.util import *
from xbake.mscan import scrapers


class MCMP:
    """mkey enum"""
    NOMATCH = 0
    RENAMED = 1
    NOCHG = 2

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
    cscraper = xconfig.scan['scraper'].lower()
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
            scrapers.tvdb(xsea, tdex, xconfig)
        elif cscraper == 'mal':
            scrapers.mal(xsea, tdex, xconfig)
        elif cscraper in ['none', 'disable', 'disabled', 'off', 'no', '0', '', None, False, 0]:
            logthis("Scraper disabled; scan.scraper =", suffix=str(cscraper), loglevel=LL.VERBOSE)
        else:
            failwith(ER.NOTIMPL, "Scraper [%s] not implemented. Unable to continue. Aborting." % (cscraper))

    return show_count


def series_add(sname, ovrx=None):
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
        if ovrx is not None:
            if 'tvdb_id' in ovrx: tdex[snamex]['tvdb_id'] = ovrx['tvdb_id']
            if 'mal_id' in ovrx: tdex[snamex]['mal_id'] = ovrx['mal_id']

    return snamex


def get_tdex():
    """return tdex object"""
    return tdex
