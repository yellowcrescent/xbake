#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# out - xbake/mscan/out.py
# XBake: Scanner output module
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_xbake
#
# Copyright (c) 2015 J. Hipps / Neo-Retro Group
#
# https://ycnrg.org/
#
###############################################################################

import __main__
import sys
import os
import re
import json
import signal
import time
import socket

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith
from xbake.common.logthis import print_r

from xbake.xcode import ffmpeg
from xbake.mscan import util
from xbake.common import db

def to_mongo(indata,moncon):
    """
    Write MScan output to Mongo
    """
    # Fix hostname
    hostname = indata['scan']['hostname'].replace('.','_')

    # Connect to Mongo
    monjer = db.mongo(moncon)

    ## Insert Series & Episode Data

    slist = []
    eplist = []
    for sname,sdata in indata['series'].iteritems():
        thisx = {}

        # if ctitle not set, skip this series
        # XXX-TODO: Possibly change this behaviour in the future
        if not sdata.get('ctitle',False):
            continue

        # Generate Series ID
        tser_id = mkid_series(sname,sdata)
        # Store this for later; will be used to check if this series was updated during this round
        indata['series'][sname]['_id'] = tser_id
        logthis("** Series ID:",suffix=tser_id,loglevel=LL.DEBUG)

        # Build entry
        thisx = {
                    '_id': tser_id,
                    'norm_id': sname,
                    'title': sdata['title'],
                    'count': sdata['count'],
                    'genre': sdata['genre'],
                    'xrefs': sdata['xrefs'],
                    'tv': sdata['tv'],
                    'ctitle': sdata['ctitle'],
                    'synopsis': sdata['synopsis'],
                    'lastupdated': sdata['lastupdated'],
                    'artwork': sdata['artwork']
                }

        # Process episodes
        for epnum,epdata in enumerate(sdata['episodes']):
            thisep = epdata

            # Generate Episode ID
            tep_id = mkid_episode(tser_id, epdata)
            # Store this for later; will be used to check if this episode was updated during this round
            indata['series'][sname]['episodes'][epnum]['_id'] = tep_id
            logthis("** Episode ID:",suffix=tep_id,loglevel=LL.DEBUG)

            thisep['tvdb_id'] = epdata['id']
            thisep['sid'] = tser_id
            del(thisep['id'])

            eplist.append(thisep)

        slist.append(thisx)

    # Insert into Mongo
    logthis("Inserting series data into Mongo...",loglevel=LL.VERBOSE)
    monjer.insert_many("series", slist)
    logthis("Inserting episode data into Mongo...",loglevel=LL.VERBOSE)
    monjer.insert_many("episodes", eplist)

    ## Insert Source File data
    xfiles = {}
    files_skipped = 0
    files_upserted = 0
    for fname,fdata in indata['files'].iteritems():
        thisf = {}
        md5 = fdata['checksum']['md5']

        # Check if unchanged
        if fdata['status'] == "unchanged":
            logthis("File already exists, and is unchanged. Skipping.",loglevel=LL.VERBOSE)
            files_skipped += 1
            continue

        # Check if entry already exists
        exist_entry = monjer.findOne("files", { '_id': md5 })
        if exist_entry:
            thisf = exist_entry

        thisf['status'] = fdata['status']
        thisf['checksum'] = fdata['checksum']
        thisf['mediainfo'] = fdata['mediainfo']
        thisf['fparse'] = {
                            'series': fdata['fparse']['series'],
                            'season': int(fdata['fparse']['season']),
                            'episode': int(fdata['fparse']['episode']),
                            'special': fdata['fparse']['special']
                          }
        thisf['tdex_id'] = fdata['tdex_id']

        # Don't overwrite these values if entry already exists
        if not exist_entry:
            # XXX-TODO: Why in the hell don't we just query mongo for every entry?
            # Check if series info was updated as part of this submission or scan
            if indata['series'].has_key(fdata['tdex_id']):
                thisf['series_id'] = indata['series'][fdata['tdex_id']]['_id']
                thisf['episode_id'] = find_matching_episode(indata['series'][fdata['tdex_id']], fdata['fparse'])
            else:
                # Query Mongo for matching series and episode IDs
                xepi_info = None
                xser_info = monjer.findOne("series", { 'norm_id': fdata['tdex_id'] })
                if xser_info:
                    xepi_info = monjer.findOne("episodes", { 'sid': xser_info['_id'], 'EpisodeNumber': str(fdata['fparse']['episode']), 'SeasonNumber': str(fdata['fparse']['season']) })

                if xepi_info:
                    thisf['series_id'] = xser_info['_id']
                    thisf['episode_id'] = xepi_info['_id']
                else:
                    thisf['series_id'] = None
                    thisf['episode_id'] = None

        # Create location for this source
        if not thisf.has_key('location'):
            thisf['location'] = {}

        thisf['location'][hostname] = {
                                        'tstamp': long(indata['scan']['tstamp']),
                                        'dpath': fdata['dpath'],
                                        'fpath': fdata['fpath'],
                                        'stat' : fdata['stat'],
                                        'mkey_id': fdata['mkey_id']
                                      }
        # Upsert
        logthis("** File ID:",suffix=md5,loglevel=LL.DEBUG)
        monjer.upsert("files", md5, thisf)
        files_upserted += 1

    # Build status information
    status_out = {
                    'ok': True,
                    'status': None,
                    'message': None,
                    'series': len(slist),
                    'episodes': len(eplist),
                    'files': files_upserted,
                    'files_skipped': files_skipped
                 }

    if files_upserted < 1:
        status_out['http_status'] = "224 Insufficient Data"
        status_out['status'] = "warning"
        status_out['message'] = "No files were added"
    else:
        status_out['http_status'] = "220 Success"
        status_out['status'] = "ok"
        status_out['message'] = "Completed without errors or warnings"

    return status_out


def to_file(indata,fname):
    """
    Write MScan output to file (or stdout)
    """
    try:
        fo = open(fname,"w")
        fo.write(json.dumps(indata,indent=4,separators=(',', ': ')))
        fo.close()
    except:
        logthis("Failed to write data to outfile:",suffix=fname,loglevel=LL.ERROR)
        failwith(ER.OPT_BAD, "Unable to write to outfile. Aborting.")


def mkid_series(tdex_id,xdata):
    """
    Create unique series ID
    """
    if xdata['tv'].get('debut',None):
        dyear = str(time.gmtime(float(xdata['tv'].get('debut'))).tm_year)
    else:
        dyear = "90" + str(int(time.time()))[-5:]
    idout = "%s.%s" % (tdex_id, dyear)
    return idout


def mkid_episode(sid,xdata):
    """
    Create unique episode ID
    """
    if xdata.get('id',None):
        isuf = xdata['id']
    else:
        isuf = str(time.time()).split('.')[1]
    idout = "%s.%s.%s.%s" % (sid,str(int(xdata.get('SeasonNumber',0))),str(int(xdata.get('EpisodeNumber',0))),isuf)
    return idout


def find_matching_episode(sdex,fpinfo):
    """
    Find matching episode (season and episode number) from submitted entries
    """
    episode_id = int(fpinfo.get('episode',0))
    season_id = int(fpinfo.get('season',0))
    for epi,epdata in enumerate(sdex['episodes']):
        if int(epdata['SeasonNumber']) == season_id:
            if int(epdata['EpisodeNumber']) == episode_id:
                return epdata['_id']

    return None