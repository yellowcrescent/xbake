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
    vername = None
    class sub:
        track = None
        type = None
        tdata = None
    class aud:
        track = None
        type = None
        channels = None
    class infile:
        file = None
        path = None
        base = None
        ext  = None
        full = None
    class outfile:
        file = None
        path = None
        base = None
        ext = '.mp4'
        full = None

class ffo:
    """
    ffmpeg options
    """
    scaler = []
    subs = []
    audio = []
    video = []
    filters = []

# Mongo object
monjer = None

def run(infile,outfile=None,vername=None,id=None,**kwargs):
    """
    Implements --xcode mode
    """
    global monjer
    conf = __main__.xsetup.config

    # Check input filename
    if not infile:
        failwith(ER.OPT_MISSING, "option infile required (-i/--infile)")
    else:
        if not os.path.exists(infile):
            failwith(ER.OPT_BAD, "infile [%s] does not exist" % infile)
        elif not os.path.isfile(infile):
            failwith(ER.OPT_BAD, "infile [%s] is not a regular file" % infile)

    # Get video ID (MD5 sum by default)
    if conf['vid']['autoid']:
        vinfo.id = util.md5sum(infile)
        logthis("MD5 Checksum:",suffix=vinfo.id,loglevel=LL.INFO)
    elif conf['run']['id']:
        vinfo.id = conf['run']['id']

    # Connect to Mongo
    monjer = db.mongo(conf['mongo'])

    # Build pre-transcode data
    vinfo.vername = vername
    if monjer and vinfo.id:
        vdata = vdataBuild()
    else:
        logthis("Setting update mode to MXM.NONE",loglevel=LL.DEBUG)
        vinfo.mxmode = MXM.NONE
        vdata = False

    # Perform transcoding
    vvdata = transcode(infile,outfile)
    if vdata:
        vdata['versions'][vinfo.vername] = vvdata

    # Grab an interesting frame for the screenshot
    if conf['run']['vscap']:
        vsdata = sscapture(infile,conf['run']['vscap'])
        if vdata:
            vdata['vscap'] = vsdata

    # Insert data into Mongo
    if vdata:
        vdataInsert(vdata)

    logthis("*** Transcoding task completed successfully.",loglevel=LL.INFO)

def sscapture(infile,offset):
    """
    Screenshot capture
    """
    conf = __main__.xsetup.config

    # split up infile
    i_real = os.path.realpath(os.path.expanduser(infile))
    i_path,i_file = os.path.split(infile)
    i_base,i_ext  = os.path.splitext(i_file)

    # build filename & path stuffs
    ssout   = i_base + '.png'
    ssoutwp = i_base + '.webp'
    ssdir = os.path.realpath(os.path.expanduser(conf['vscap']['basedir']))
    ssdir_full = conf['vscap']['basedir'] + '/full'
    ssdir_480 = conf['vscap']['basedir'] + '/480'
    ssdir_240 = conf['vscap']['basedir'] + '/240'
    ssout_full = os.path.realpath(ssdir_full + '/' + ssout)
    ssout_fullwp = os.path.realpath(ssdir_full + '/' + ssoutwp)
    ssout_480 = os.path.realpath(ssdir_480 + '/' + ssout)
    ssout_480wp = os.path.realpath(ssdir_480 + '/' + ssoutwp)
    ssout_240 = os.path.realpath(ssdir_240 + '/' + ssout)
    ssout_240wp = os.path.realpath(ssdir_240 + '/' + ssoutwp)

    # grab the frame
    logthis("Capturing frame at offset:",suffix=offset,loglevel=LL.INFO)
    ffmpeg.vscap(i_real, offset, ssout_full)

    # scale to smaller versions; convert all versions to WebP
    logthis("Generating intermediate sizes and WebP versions",loglevel=LL.VERBOSE)
    ffmpeg.im_scale(ssout_full, ssout_480, 480)
    ffmpeg.im_scale(ssout_full, ssout_240, 240)
    ffmpeg.webp_convert(ssout_full, ssout_fullwp)
    ffmpeg.webp_convert(ssout_480, ssout_480wp)
    ffmpeg.webp_convert(ssout_240, ssout_240wp)

    logthis("Screenshot generation complete.",ccode=C.GRN,loglevel=LL.INFO)

    # Set vscap vdata
    vsdata = { 'filename': ssout, 'offset': offset }

    return vsdata


def transcode(infile,outfile=None):
    """
    Transcode video
    """
    global monjer
    conf = __main__.xsetup.config

    # Split apart the input file, path, and extension
    vinfo.infile.full = os.path.realpath(os.path.expanduser(infile))
    vinfo.infile.path,vinfo.infile.file = os.path.split(vinfo.infile.full)
    vinfo.infile.base,vinfo.infile.ext  = os.path.splitext(vinfo.infile.file)

    # Get Matroska data
    logthis("Getting Matroska data",loglevel=LL.DEBUG)
    mkv = getMatroska(vinfo.infile.full)

    ## Set up encoding options ##

    ## Subtitles
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
            logthis("** Subs: Track %d (%s) - '%s' [%s] %s" % (st['number'] - 1,st['codec_id'],st['name'],st['language'],strifset(st['default'],"***")),loglevel=LL.INFO)
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

        # Set ffmpeg options for subs
        # For ASS subs, dump font attachments
        if vinfo.sub.type == STYPE.ASS:
            logthis("Dumping font attachments...",loglevel=LL.INFO)
            fontlist = ffmpeg.dumpFonts(vinfo.infile.full)
            subfile = "subtrack.ass"
            ffo.subs = [ 'ass=%s' % subfile ]
        elif vinfo.sub.type == STYPE.SRT:
            subfile = "subtrack.srt"
            ffo.subs = [ "subtitles=%s:force_style='%s'" % (subfile, conf['xcode']['srt_style']) ]
        else:
            logthis("Unsupported subtitle type:",suffix=vinfo.sub.type,loglevel=LL.ERROR)
            failwith(ER.UNSUPPORTED, "Sub type not supported. Unable to continue. Aborting.")

        # Extract subtitle track
        logthis("Extracting subtitle track from container...",loglevel=LL.INFO)
        ffmpeg.dumpSub(vinfo.infile.full, vinfo.sub.track, subfile)

    ## Audio
    atracks = mkv['audio_tracks']

    if conf['xcode']['aid']:
        subset = conf['xcode']['aid']
    else:
        subset = True

    for st in atracks:
        logthis("** Audio: Track %d (%s) - '%s' %dch [%s] %s" % (st['number'] - 1,st['codec_id'],st['name'],st['channels'],st['language'],strifset(st['default'],"***")),loglevel=LL.INFO)
        if st['default']: deftrack = st
        if subset == (st['number'] - 1): vinfo.aud.tdata = st
    # if no track found, use default
    if not vinfo.aud.tdata:
        # throw a warning if our chosen track doesn't exist
        if subset is not True and subset != (deftrack['number'] - 1):
            logthis("Using default audio track. Track not found with ID",suffix=subset,loglevel=LL.WARNING)
        vinfo.aud.tdata = deftrack

    # Get important bits of track data
    vinfo.aud.track = vinfo.aud.tdata['number'] - 1
    vinfo.aud.type  = vinfo.aud.tdata['codec_id']
    vinfo.aud.channels = vinfo.aud.tdata['channels']

    # Determine if we need to transcode the audio
    if conf['xcode']['acopy'].lower() == 'auto':
        # stream copy apparently only works for the default track
        if vinfo.aud.type == 'A_AAC' and vinfo.aud.tdata['default']:
            vinfo.aud.copy = True
        else:
            vinfo.aud.copy = False
    elif conf['xcode']['acopy'] == 1 or conf['xcode']['acopy'] is True:
        vinfo.aud.copy = True
    else:
        vinfo.aud.copy = False

    # Determine if we need to downmix/upmix
    if conf['xcode']['downmix'].lower() == 'auto':
        if vinfo.aud.channels != 2:
            vinfo.aud.downmix = True
            # If stream copy is also set to auto, make sure it's
            # disabled if we need to downmix
            if conf['xcode']['acopy'].lower() == 'auto':
                vinfo.aud.copy = False
        else:
            vinfo.aud.downmix = False
    elif conf['xcode']['downmix'] == 1 or conf['xcode']['downmix'] is True:
        vinfo.aud.downmix = True
    else:
        vinfo.aud.downmix = False

    # Set audio encoding options
    if vinfo.aud.copy:
        # stream copy
        ffo.audio += [ '-c:a', 'copy' ]
    else:
        # set codec
        ffo.audio += [ '-c:a:%d' % vinfo.aud.track, 'libfaac' ]
        # set audio bitrate
        ffo.audio += [ '-b:a:%d' % vinfo.aud.track, '%dk' % conf['xcode']['abr'] ]
        # set downmix (or possibly upmix if mono), if enabled
        if vinfo.aud.downmix: ffo.audio += [ '-ac', '2' ]

    ## Filtering
    if conf['xcode']['scale']:
        ffo.scaler = [ 'scale=%s' % conf['xcode']['scale'] ]
    if conf['xcode']['anamorphic']:
        ffo.scaler = [ 'scale=854:480' ]
        ffo.video += [ '-aspect', '16:9' ]

    # prefix filters to ffo.video
    if ffo.scaler or ffo.subs:
        ffo.video = [ '-vf', ','.join(ffo.scaler + ffo.subs) ] + ffo.video

    ## Video & Output filename
    ffo.video += [ '-c:v', 'libx264', '-crf', '20', '-preset:v', 'medium' ]

    # Get output path
    if outfile and os.path.isdir(outfile):
        vinfo.outfile.path = os.path.realpath(os.path.expanduser(outfile))
    else:
        vinfo.outfile.path = os.path.realpath('.')

    # Select output container & extension
    if not conf['xcode']['flv']:
        ffo.video += [ '-movflags', '+faststart' ]
        vinfo.outfile.ext = '.mp4'
    else:
        vinfo.outfile.ext = '.flv'

    # Get output filename
    if outfile and not os.path.isdir(outfile):
        vinfo.outfile.path,vinfo.outfile.file = os.path.split(os.path.realpath(os.path.expanduser(outfile)))
        vinfo.outfile.base,vinfo.outfile.ext = os.path.split(vinfo.outfile.file)
    else:
        vinfo.outfile.base = vinfo.infile.base

    # Outfile realpath
    vinfo.outfile.full = vinfo.outfile.path + '/' + vinfo.outfile.base + vinfo.outfile.ext
    vinfo.outfile.file = os.path.split(vinfo.outfile.full)[1]


    logthis("-- Using Subtitle Track:",suffix=vinfo.sub.track,loglevel=LL.INFO)
    logthis("-- Using Audio Track:",suffix=vinfo.aud.track,loglevel=LL.INFO)
    logthis("-- Output filename:",suffix=vinfo.outfile.full,loglevel=LL.INFO)

    ## Build ffmpeg command
    ffoptions = [ '-y', '-i', vinfo.infile.full ] + ffo.video + ffo.audio + [ vinfo.outfile.full ]
    ffmpeg.run(ffoptions)

    ## Cleanup
    logthis("Removing font and subtitle files...",loglevel=LL.VERBOSE)
    os.remove(subfile)
    for ff in fontlist: os.remove(ff)

    logthis("Transcoding complete",ccode=C.GRN,loglevel=LL.INFO)

    if vinfo.vername:
        vvdata = {
                    'encoder': { 'encode': ' '.join(ffoptions) },
                    'mediainfo': util.mediainfo(vinfo.outfile.full),
                    'location': {
                        'uri': vinfo.vername + '/' + vinfo.outfile.file,
                        'realpath': vinfo.outfile.full
                    }
                 }
    else:
        vvdata = None

    return vvdata


def vdataInsert(xvid):
    """
    Insert data into MongoDB collection
    """
    global monjer

    logthis("Inserting data into Mongo...",loglevel=LL.INFO)
    if vinfo.mxmode == MXM.INSERT:
        monjer.insert('videos',xvid)
    elif vinfo.mxmode == MXM.UPDATE:
        vsetter = { 'versions.'+vinfo.vername : xvid['versions'][vinfo.vername] }
        monjer.update_set('videos',vinfo.id,vsetter)


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
            xvid = False
    else:
        logthis("No matching entry found in database. ID:",suffix=vinfo.id,loglevel=LL.ERROR)
        failwith(ER.NOTFOUND, "No match for VID. Will not contiue. Aborting.")

    return xvid

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
