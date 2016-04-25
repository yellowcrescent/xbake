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
import requests
from datetime import datetime

# Logging & Error handling
from xbake.common.logthis import C,LL,logthis,ER,failwith,loglevel,print_r

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

    ## Upsert all the things into Mongo

    # Build the up2date matrix
    up2dater = {
                'series': { 'new': 0, 'updated': 0, 'nc': 0, 'total': 0, 'upserted': 0, 'errors': 0 },
                'episodes': { 'new': 0, 'updated': 0, 'nc': 0, 'total': 0, 'upserted': 0, 'errors': 0 },
                'files': { 'new': 0, 'updated': 0, 'nc': 0, 'total': 0, 'upserted': 0, 'errors': 0 }
               }

    # Series Data
    logthis("Inserting series data into Mongo...",loglevel=LL.VERBOSE)
    for tk,tss in enumerate(slist):
        # Process each series
        tssid = tss.get('_id')
        logthis("** Series:",prefix=tssid,suffix=tss.get("title",tssid),loglevel=LL.DEBUG)
        thisup = int(tss.get("lastupdated",0))
        up2dater['series']['total'] += 1

        # Check for existing entry
        txo = monjer.findOne("series", { "_id": tssid })
        if txo:
            lastup = int(txo.get("lastupdated",0))
            logthis("-- Last Updated:",prefix=tssid,suffix="%s (%d)" % (datetime.utcfromtimestamp(lastup).strftime("%d %b %Y %H:%M:%S"), lastup),loglevel=LL.DEBUG)
        else:
            txo = {}
            lastup = -1
        logthis("-- This Updated:",prefix=tssid,suffix="%s (%d)" % (datetime.utcfromtimestamp(thisup).strftime("%d %b %Y %H:%M:%S"), thisup),loglevel=LL.DEBUG)

        # Check if this entry is newer than the existing one
        if thisup > lastup:
            try:
                # Use dict.update() so we can retain extra fields for entries being updated
                txo.update(tss)
                monjer.upsert("series",tssid,txo)
                up2dater['series']['upserted'] += 1
                if lastup > 0:
                    logthis(">> Series updated OK!",prefix=tssid,loglevel=LL.VERBOSE)
                    up2dater['series']['updated'] += 1
                else:
                    logthis("++ Series inserted OK!",prefix=tssid,loglevel=LL.VERBOSE)
                    up2dater['series']['new'] += 1
            except Exception as e:
                logthis("!! Series upsert failed.",prefix=tssid,suffix=e,loglevel=LL.ERROR)
                up2dater['series']['errors'] += 1
        else:
            logthis("!! Existing entry up-to-date",prefix=tssid,loglevel=LL.VERBOSE)
            up2dater['series']['nc'] += 1


    # Episode Data
    logthis("Inserting episode data into Mongo...",loglevel=LL.VERBOSE)
    for tk,tss in enumerate(eplist):
        # Process each series
        tssid = tss.get('_id')
        logthis("** Episode:",prefix=tssid,suffix="S:%s/E:%s \"%s\"" % (tss.get("SeasonNumber",""),tss.get("EpisodeNumber",""),tss.get("EpisodeName","")),loglevel=LL.DEBUG)
        thisup = int(tss.get("lastupdated",0))
        up2dater['episodes']['total'] += 1

        # Check for existing entry
        txo = monjer.findOne("episodes", { "_id": tssid })
        if txo:
            lastup = int(txo.get("lastupdated",0))
            logthis("-- Last Updated:",prefix=tssid,suffix="%s (%d)" % (datetime.utcfromtimestamp(lastup).strftime("%d %b %Y %H:%M:%S"), lastup),loglevel=LL.DEBUG)
        else:
            txo = {}
            lastup = -1
        logthis("-- This Updated:",prefix=tssid,suffix="%s (%d)" % (datetime.utcfromtimestamp(thisup).strftime("%d %b %Y %H:%M:%S"), thisup),loglevel=LL.DEBUG)

        # Check if this entry is newer than the existing one
        if thisup > lastup:
            try:
                # Use dict.update() so we can retain extra fields for entries being updated
                txo.update(tss)
                monjer.upsert("episodes",tssid,txo)
                up2dater['episodes']['upserted'] += 1
                if lastup > 0:
                    logthis(">> Episode updated OK!",prefix=tssid,loglevel=LL.VERBOSE)
                    up2dater['episodes']['updated'] += 1
                else:
                    logthis("++ Episode inserted OK!",prefix=tssid,loglevel=LL.VERBOSE)
                    up2dater['episodes']['new'] += 1
            except Exception as e:
                logthis("!! Episode upsert failed.",prefix=tssid,suffix=e,loglevel=LL.ERROR)
                up2dater['episodes']['errors'] += 1
        else:
            logthis("!! Existing entry up-to-date",prefix=tssid,loglevel=LL.VERBOSE)
            up2dater['episodes']['nc'] += 1


    ## Insert Source File data
    xfiles = {}
    for fname,fdata in indata['files'].iteritems():
        thisf = {}
        md5 = fdata['checksum']['md5']
        up2dater['files']['total'] += 1

        # Check if unchanged
        if fdata['status'] == "unchanged":
            logthis("File already exists, and is unchanged. Skipping.",loglevel=LL.VERBOSE)
            up2dater['files']['nc'] += 1
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
            up2dater['files']['new'] += 1
        else:
            up2dater['files']['updated'] += 1

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
        up2dater['files']['upserted'] += 1


    # Build status information
    status_out = {
                    'ok': True,
                    'status': None,
                    'message': None,
                    'stats': up2dater
                 }

    if up2dater['files']['upserted'] < 1:
        status_out['http_status'] = "216 Nothing Added"
        status_out['status'] = "warning"
        status_out['message'] = "No files were added"
    else:
        status_out['http_status'] = "201 Content Added"
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
        xstat = { 'status': "ok" }
    except:
        logthis("Failed to write data to outfile:",suffix=fname,loglevel=LL.ERROR)
        xstat = { 'status': "error", 'message': "Failed to write data to outfile" }

    return xstat


def to_server(indata,shost):
    """
    Send results to listening XBake daemon
    """
    shared_key = __main__.xsetup.config['srv']['shared_key']
    logthis("Server prefix:",suffix=shost,loglevel=LL.DEBUG)
    logthis("Shared key:",suffix=shared_key,loglevel=LL.DEBUG)

    # Create request
    qurl = shost + "/api/mscan/add"
    headset = { 'Content-Type': "application/json", 'WWW-Authenticate': shared_key, 'User-Agent': "XBake/"+__main__.xsetup.version }
    logthis("** Sending data to",suffix=qurl,loglevel=LL.VERBOSE)
    rq = requests.post(qurl,headers=headset,data=json.dumps(indata))

    # Process response
    if rq.status_code == 201:
        logthis("** Data sent to remote server successfully!",suffix=str(rq.status_code)+' '+rq.reason,loglevel=LL.INFO)
        xstat = { 'status': "ok" }
    elif rq.status_code == 216:
        logthis("** Server reported that no new data was added (0 new entries)",suffix=str(rq.status_code)+' '+rq.reason,loglevel=LL.WARNING)
        xstat = { 'status': "warning", 'message': "Server reported that no new data was added (0 new entries)" }
    elif rq.status_code == 500:
        logthis("** Server failed while processing the request.",suffix=str(rq.status_code)+' '+rq.reason,loglevel=LL.ERROR)
        xstat = { 'status': "error", 'message': "Server failed while processing the request" }
    else:
        logthis("** Server sent back an invalid response.",suffix=str(rq.status_code)+' '+rq.reason,loglevel=LL.ERROR)
        xstat = { 'status': "error", 'message': "Server sent back an invalid response" }

    return xstat

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
    for epi,epdata in enumerate(sdex.get('episodes',[])):
        if int(epdata['SeasonNumber']) == season_id:
            if int(epdata['EpisodeNumber']) == episode_id:
                return epdata['_id']

    return None