#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.mscan.scrapers.tvdb
Scrapers: TheTVDb.com

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import os
import re
import time

import requests
import xmltodict
import arrow

from xbake import __version__
from xbake.common.logthis import *
from xbake.mscan.util import *

__desc__ = "TheTVDb.com"
__author__ = "J. Hipps <jacob@ycnrg.org>"
__version__ = "1.0.0"
__date__ = "25 Nov 2016"


def run(xsea, tdex, config):
    """
    TheTVDB.com (TVDB) Scraper
    """
    xstitle = tdex[xsea]['title']
    logthis("Retrieving series information from theTVDb for", suffix=xstitle, loglevel=LL.VERBOSE)

    tvdb_id = tdex[xsea].get('tvdb_id', tvdb_get_id(xstitle, config))

    if tvdb_id:
        if tdex[xsea].has_key('tvdb_id'):
            logthis("tvdb_id set from override", loglevel=LL.VERBOSE)
            del(tdex[xsea]['tvdb_id'])
        logthis("Got theTVDb Series ID#", suffix=tvdb_id, loglevel=LL.VERBOSE)

        # Retrieve entry from TVDB
        tvdb_info = tvdb_get_info(tvdb_id, config)
        tdex[xsea].update(tvdb_process(tvdb_info, config, xsea))
        logthis("theTVDb info:", suffix=tvdb_info, loglevel=LL.DEBUG2)
        return True
    else:
        logthis("No results in theTVDb found for series", suffix=xstitle, loglevel=LL.WARNING)
        return False


def tvdb_get_id(sername, config):
    """
    TVDB: Get SeriesID from SeriesName
    """
    # Query TVDb for SeriesName
    xresp = getxml(config.tvdb['mirror'] + "/api/GetSeries.php", {'seriesname': sername})
    logthis("Got response from TVDb:", suffix=print_r(xresp), loglevel=LL.DEBUG2)

    snorm = normalize(sername)
    dres = xresp['answer'].get('Data', False)

    if dres:
        # Check if single or multiple results found
        xser = dres.get('Series')
        if isinstance(xser, list):
            logthis("Multiple results found", loglevel=LL.DEBUG)
            xsout = None
            for sv in xser:
                # Check against main SeriesName
                if normalize(sv.get('SeriesName', '')) == snorm:
                    logthis("Choosing exact match against SeriesName", loglevel=LL.DEBUG)
                    xsout = sv
                    break
                else:
                    # Check against AliasNames
                    xalias = sv.get('AliasNames', '').split('|')
                    for curali in xalias:
                        if normalize(curali) == snorm:
                            logthis("Choosing exact match against AliasNames", loglevel=LL.DEBUG)
                            xsout = sv
                            break
        else:
            logthis("Single match returned", loglevel=LL.DEBUG)
            xsout = xser

        if xsout:
            xid_out = xsout['seriesid']
            logthis("** SeriesID: %s / SeriesName: %s / AliasNames: %s" % (xsout.get('seriesid', ''), xsout.get('SeriesName', ''), xsout.get('AliasNames', '')), loglevel=LL.VERBOSE)
        else:
            logthis("No exact match or alias match found. Choosing none.", prefix=sername, loglevel=LL.WARNING)
            xid_out = False
    else:
        logthis("Malformed or invalid response from theTVDb", loglevel=LL.ERROR)
        xid_out = False

    return xid_out


def tvdb_get_info(serid, config, slang="en"):
    """
    TVDB: Retrieve series info
    """
    # Retrieve series data from TVDb
    xresp = getxml("%s/api/%s/series/%s/all/%s.xml" % (config.tvdb['mirror'], config.tvdb['apikey'], serid, slang))
    logthis("Got response from TVDb:", suffix=print_r(xresp), loglevel=LL.DEBUG2)

    if xresp['ok']:
        logthis("Retrieved series info OK", loglevel=LL.DEBUG)
        xdout = xresp['answer'].get('Data', False)
    else:
        logthis("Failed to retrieve series information from TVDb. return code =", suffix=xresp['status'], loglevel=LL.WARNING)
        xdout = False

    return xdout


def tvdb_process(indata, config, tdex_id):
    """
    TVDB: Process data and enumerate artwork assets
    """
    txc = {
            'tv': {}, 'xrefs': {}, 'synopsis': {}, 'xref': {},
            'artwork': {}, 'episodes': []
          }

    iser = indata.get('Series', {})

    logthis("Processing info from theTVDb; enumerating artwork assets", loglevel=LL.VERBOSE)

    # Get list of genres; filter out any empty entries
    txc['genre'] = safe_split(iser.get('Genre', ''))

    # Get attributes
    txc['ctitle'] = iser.get('SeriesName', None)
    txc['xrefs']['tvdb'] = iser.get('id', None)
    txc['xrefs']['imdb'] = iser.get('IMDB_ID', None)
    txc['lastupdated'] = long(iser.get('lastupdated', time.time()))
    txc['tv']['network'] = iser.get('Network', None)
    txc['tv']['dayslot'] = iser.get('Airs_DayOfWeek', None)
    txc['tv']['timeslot'] = iser.get('Airs_Time', None)
    txc['tv']['debut'] = date2time(iser.get('FirstAired', None))
    txc['synopsis']['tvdb'] = iser.get('Overview', None)
    txc['default_synopsis'] = 'tvdb'
    txc['status'] = iser.get('Status', 'unknown').lower()

    txc['fetched'] = long(time.time())

    # Generate series ID
    txc['_id'] = mkid_series(tdex_id, txc)

    # Get artwork defaults
    bandefs = {}
    bandefs['banners'] = iser.get('banner', None)
    bandefs['fanart'] = iser.get('fanart', None)
    bandefs['poster'] = iser.get('poster', None)

    # Get Artwork
    txc['artwork'] = tvdb_get_artwork(txc['xrefs']['tvdb'], config, bandefs)

    # Add Episode information
    txc['episodes'] = tvdb_process_episodes(indata.get('Episode', []), txc['_id'])

    logthis("Series metadata set.", loglevel=LL.VERBOSE)

    return txc


def tvdb_process_episodes(epdata, series_id):
    """
    TVDB: Process episode data; returns a list of episodes
    """
    epo = []
    for tepi in epdata:
        trow = {
                '_id': mkid_episode(series_id, tepi),
                'series_id': series_id,
                'season': int(tepi.get('SeasonNumber')),
                'episode': int(tepi.get('EpisodeNumber')),
                'episode_absolute': None,
                'title': tepi.get('EpisodeName'),
                'alt_titles': [],
                'first_aired': None,
                'lang': tepi.get('Language'),
                'lastupdated': int(tepi.get('lastupdated', int(time.time()))),
                'people': {'director': safe_split(tepi.get('Director', '')),
                           'writers': safe_split(tepi.get('Writer', '')),
                           'guests': safe_split(tepi.get('GuestStars', '')),
                           'actors': []},
                'xref': {'tvdb': tepi.get('id'), 'tvdb_season': tepi.get('seasonid'),
                         'tvdb_series': tepi.get('seriesid'), 'imdb': tepi.get('IMDB_ID'),
                         'production_code': tepi.get('ProductionCode')},
                'synopsis': {'tvdb': tepi.get('Overview')},
                'default_synopsis': 'tvdb',
                'scrape_time': int(time.time())
               }
        if tepi.get('absolute_number') is not None:
            try:
                trow['episode_absolute'] = int(tepi.get('absolute_number'))
            except Exception as e:
                logexc(e, "Failed to parse absolute_number for %s" % (trow['_id']))
        try:
            if tepi.get('FirstAired') is not None:
                trow['first_aired'] = arrow.get(tepi.get('FirstAired')).timestamp
        except Exception as e:
            logexc(e, "Failed to parse date from FirstAired value for %s" % (trow['_id']))
        epo.append(trow)

    return epo


def tvdb_get_artwork(serid, config, adefs={}):
    """
    TVDB: Fetch artwork data
    """
    imgbase = config.tvdb['imgbase']

    xdout = {'banners': [], 'fanart': [], 'poster': [], 'season': []}

    # Retrieve artwork data from TVDb
    logthis("Fetching artwork/banner data from theTVDb...", loglevel=LL.INFO)
    xresp = getxml("%s/api/%s/series/%s/banners.xml" % (config.tvdb['mirror'], config.tvdb['apikey'], serid))
    logthis("Got response from TVDb:", suffix=print_r(xresp), loglevel=LL.DEBUG2)

    if xresp['ok']:
        logthis("Retrieved banner info OK", loglevel=LL.DEBUG)
        blist = xresp['answer'].get('Banners', {}).get('Banner', [])

        for bb in blist:
            bantype = bb.get('BannerType', '').lower().strip()
            if config.run['tsukimi']:
                tart = {
                        'id': bb.get('id', False),
                        'source': "tvdb",
                        'lang': bb.get('Language', None),
                        'url': '%s/%s' % (imgbase, bb.get('BannerPath', '')),
                        'path': bb.get('BannerPath', ''),
                        'type2': bb.get('BannerType2', False),
                        'season': int(bb.get('Season', '0')),
                        'default': False,
                        'selected': False
                       }
            else:
                tart = {
                        'url': '%s/%s' % (imgbase, bb.get('BannerPath', '')),
                        'path': bb.get('BannerPath', ''),
                        'type2': bb.get('BannerType2', False),
                        'tvdb_id': bb.get('id', False),
                        'lang': bb.get('Language', None),
                        'season': bb.get('Season', '0'),
                        'default': False,
                        'selected': False
                       }
            if re.match('^(banner|fanart|poster|series|season)$', bantype):
                if bantype == 'series': bantype = 'banners'
                if bantype != 'season':
                    if tart['path'] == adefs.get(bantype, False):
                        tart['default'] = True
                xdout[bantype].append(tart)
            else:
                logthis("Unknown banner type encountered. bantype =", suffix=bantype, loglevel=LL.VERBOSE)

    else:
        logthis("Failed to retrieve series banner information from TVDb. return code =", suffix=xresp['status'], loglevel=LL.WARNING)
        xdout = {}

    logthis("Artwork check complete. Banners: %d / Fanart: %d / Poster: %d / Season: %d" % (len(xdout['banners']), len(xdout['fanart']), len(xdout['poster']), len(xdout['season'])), loglevel=LL.VERBOSE)

    return xdout


def getxml(uribase, qget=None, qauth=None):
    """
    Make HTTP request and decode XML response
    """
    useragent = "Mozilla/5.0 (compatible; XBake/"+__version__+" +https://ycnrg.org/); "+os.uname()[0]+" "+os.uname()[4]
    rstat = {'status': None, 'ok': False, 'answer': None}

    # Set headers
    rqheaders = {'User-Agent': useragent}

    # Perform request
    logthis("Performing HTTP request to:", suffix=uribase, loglevel=LL.DEBUG)
    r = requests.get(uribase, params=qget, auth=qauth, headers=rqheaders)

    # Process response
    logthis("Got response status:", suffix=str(r.status_code)+' '+r.reason, loglevel=LL.DEBUG)
    rstat['status'] = r.status_code

    # If all went well, decode the XML response
    if r.status_code == 200:
        rstat['answer'] = xmltodict.parse(r.text)
        rstat['ok'] = True

    return rstat


def date2time(dstr, fstr="%Y-%m-%d"):
    """
    Convert date string to integer UNIX epoch time
    """
    try:
        return long(time.mktime(time.strptime(dstr, fstr)))
    except Exception as e:
        logthis("strptime() conversion failed:", suffix=e, loglevel=LL.VERBOSE)
        return None


def safe_split(indata, sepchar='|'):
    """
    split string safely
    """
    try:
        return filter(lambda x: len(x.strip()), indata.split(sepchar))
    except:
        return []
