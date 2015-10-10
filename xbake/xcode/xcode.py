#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# xcode - xbake/xcode/xcode.py
# XBake: Transcoder
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_cpx
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
import subprocess
import enzyme

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith

from xbake.xcode import ffmpeg
from xbake.mscan import util
from xbake.common import db

class MXM:
    """
    Entry update modes
    """
    NONE   = 0
    INSERT = 1
    UPDATE = 2

class STYPE:
    """
    Subtitle types/codecs
    """
    ASS = 'S_TEXT/ASS'
    SRT = 'S_TEXT/UTF8'
    VOB = 'S_VOBSUB'

class vx:
    """
    Video working data
    """
    # Video metadata, will be sent directly to Mongo
    # and inserted into db.videos
    xvid = {}
    # Entry data from db.files
    fdi = {}
    # Matching entry from db.episodes
    fdi_epx = {}
    # Matching entry from db.series
    fdi_srx = {}

class vinfo:
    """
    Video identification info
    """
    id = None
    location = None
    mxmode = None
    class sub:
        track = None
        type = None
        tdata = None
    class aud:
        track = None
        type = None
    class infile:
        file = None
        path = None
        base = None
        ext  = None
        full = None

# Mongo object
monjer = None

def transcode(infile,outfile=None,vername=None,id=None,**kwargs):
    """
    Implements --xcode mode
    """
    global monjer
    conf = __main__.xsetup.config

    # Check input filename
    if not infile:
        failwith(ER.OPT_MISSING, "option infile required (-i/--infile)")
    else:
        infile = os.path.realpath(os.path.expanduser(infile))
        vinfo.infile.full = infile
        if not os.path.exists(infile):
            failwith(ER.OPT_BAD, "infile [%s] does not exist" % infile)
        elif not os.path.isfile(infile):
            failwith(ER.OPT_BAD, "infile [%s] is not a regular file" % infile)

    # Split apart the file, path, and extension
    vinfo.infile.path,vinfo.infile.file = os.path.split(infile)
    vinfo.infile.base,vinfo.infile.ext  = os.path.splitext(vinfo.infile.file)

    # Get video ID (MD5 sum by default)
    if conf['vid']['autoid']:
        vinfo.id = util.md5sum(infile)
        logthis("MD5 Checksum:",suffix=vinfo.id,loglevel=LL.INFO)
    elif conf['run']['id']:
        vinfo.id = conf['run']['id']

    # Connect to Mongo
    monjer = db.mongo(conf['mongo'])

    # Build pre-transcode data
    if monjer and vinfo.id:
        vdataBuild()
    else:
        logthis("Setting update mode to MXM.NONE",loglevel=LL.DEBUG)
        vinfo.mxmode = MXM.NONE

    # Get Matroska data
    logthis("Getting Matroska data",loglevel=LL.DEBUG)
    mkv = getMatroska(vinfo.infile.full)

    # Set up encoding options
    if trueifset(conf['run']['bake'],typematch=True):
        # Set up subtitle baking options (hardsub)
        stracks = mkv['subtitle_tracks']

        # Parse run.bake option for MKV subtitle track number (zero-based; eg. mkvmerge compatible)
        # If run.bake is 'auto' or set to True, use whichever track is marked as default
        if conf['run']['bake'].lower() == 'auto':
            subset = True
        elif conf['run']['bake'] is True:
            subset = True
        else:
            try:
                subset = int(conf['run']['bake'])
            except ValueError as e:
                logthis("Unable to parse track number for run.bake (--bake) option:",suffix=e,loglevel=LL.ERROR)
                logthis("Using whichever track is marked as default",loglevel=LL.WARNING)
                subset = True

        if len(stracks) > 1:
            logthis("Multiple subtitle tracks in source container",loglevel=LL.WARNING)

        # Loop through the tracks to find the matching track or default track
        for st in stracks:
            logthis("** Subs: Track %s (%s) - '%s' [%s] %s" % (st['number'] - 1,st['codec_id'],st['name'],st['language'],strifset(st['default'],"***")),loglevel=LL.VERBOSE)
            if st['default']: deftrack = st
            if subset == (st['number'] - 1): vinfo.sub.tdata = st
        # if no track found, use default
        if not vinfo.sub.tdata:
            # throw a warning if our chosen track doesn't exist
            if subset is not True and subset != (deftrack['number'] - 1):
                logthis("Using default subtitle track. Track not found with ID",suffix=subset,loglevel=LL.WARNING)
            vinfo.sub.tdata = deftrack

        # Get important bits of track data
        vinfo.sub.track = vinfo.sub.tdata['number'] - 1
        vinfo.sub.type  = vinfo.sub.tdata['codec_id']

        # For ASS subs, dump font attachments
        if vinfo.sub.type == STYPE.ASS:
            logthis("Dumping font attachments for subtitles",loglevel=LL.VERBOSE)
            try:
                subprocess.check_output(['ffmpeg','-y','-dump_attachment:t','','-i',vinfo.infile.full])
            except subprocess.CalledProcessError as e:
                logthis("ffmpeg got mad, but we should be OK. dump_attachment always throws an error, even when it works.",loglevel=LL.WARNING)



def vdataBuild():
    """
    Query MongoDB and build data structures prior to transcoding
    """
    global monjer

    vx.fdi = monjer.findOne('files', { '_id': vinfo.id })
    if vx.fdi:
        logthis("Found matching entry in database",loglevel=LL.INFO)
        # Get episode information
        if vx.fdi['episode_id']:
            vx.fdi_epx = monjer.findOne('episodes', { '_id': vx.fdi['episode_id'] })
            logthis("Found matching episode entry",loglevel=LL.VERBOSE)
        else:
            vx.fdi_epx = None

        # Get series information
        if vx.fdi['series_id']:
            vx.fdi_srx = monjer.findOne('series', { '_id': vx.fdi['series_id'] })
            logthis("Found matching series entry",loglevel=LL.VERBOSE)
        else:
            vx.fdi_srx = None

        # Check if matching video already exists
        if monjer.findOne('videos', { '_id': vx.fdi['_id'] }):
            logthis("Entry does not already exist. Populating video metadata",loglevel=LL.INFO)
            vinfo.mxmode = MXM.INSERT
            # Check location
            if conf['vid']['location']:
                # Get from running config (--vername option or vid.vername)
                vinfo.location = conf['vid']['location']
            else:
                # Otherwise, get first version from list
                if vx.fdi.has_key('versions') and len(vx.fdi['versions']):
                    vinfo.location = vx.fdi['versions'].keys()[0]

            # Initialize metadata
            xvid = {
                    '_id':  vx.fdi['_id'],
                    'metadata': {
                            'title': setifset(vx.fdi_epx,'EpisodeName'),
                            'series': vx.fdi['fparse']['series'],
                            'episode': vx.fdi['fparse']['episode'],
                            'season': vx.fdi['fparse']['season'],
                            'special': vx.fdi['fparse']['special']
                        },
                    'tdex_id': setifset(vx.fdi_srx,'norm_id'),
                    'series_id': vx.fdi['series_id'],
                    'episode_id': vx.fdi['episode_id'],
                    'tvdb_id': { 'series': vx.fdi_srx['xrefs']['tvdb'], 'episode': vx.fdi_epx['tvdb_id'] },
                    'source': {
                            'filename': vx.fdi['location'][vinfo.location]['fpath']['file'],
                            'location': {
                                    'hostname': vinfo.location,
                                    'path': vx.fdi['location'][vinfo.location]['fpath']['real']
                                },
                            'mediainfo': vx.fdi['mediainfo'],
                            'checksum': vx.fdi['checksum'],
                            'stat': vx.fdi['location'][vinfo.location]['stat']
                        },
                    'subs': {
                            'enabled': trueifset(conf['run']['bake'],typematch=True),
                            'lang': 'eng',
                            'fansub': setifset(conf['run'], 'fansub')
                        }
                   }
        else:
            # Entry already exists in db.videos
            logthis("Entry already exists. Will update version or vscap information.",loglevel=LL.INFO)
            vinfo.mxmode = MXM.UPDATE
    else:
        logthis("No matching entry found in database. ID:",suffix=vinfo.id,loglevel=LL.ERROR)
        failwith(ER.NOTFOUND, "No match for VID. Will not contiue. Aborting.")


def getMatroska(vfile):
    """
    Get metadata and track information from Matroska containers
    """
    try:
        with open(vfile) as f: mkv = enzyme.MKV(f)
    except MalformedMKVError as e:
        logthis("Not a Matroska container or segment is corrupt.",loglevel=LL.DEBUG)
        return False
    return mkv.to_dict()


def setifset(idict,ikey):
    if idict.has_key(ikey):
        return idict[ikey]
    else:
        return False

def trueifset(xeval,typematch=False):
    if typematch:
        if not (xeval is False or xeval is None): return True
        else: return False
    else:
        if xeval: return True
        else: return False

def strifset(xeval,iftrue,iffalse="",typematch=False):
    if typematch:
        if not (xeval is False or xeval is None): return iftrue
        else: return iffalse
    else:
        if xeval: return iftrue
        else: return iffalse
