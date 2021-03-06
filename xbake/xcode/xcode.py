#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.xcode.xcode
Transcoder

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import os
import enzyme

from xbake.common.logthis import *
from xbake.mscan.util import *
from xbake.xcode import ffmpeg
from xbake.mscan import util
from xbake.common import db

class MXM:
    """
    Entry update modes
    """
    NONE = 0
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
    # pylint: disable=missing-docstring
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
        ext = None
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
config = None


def run(xconfig):
    """
    Implements --xcode mode
    """
    global monjer, config
    config = xconfig

    # Check input filename
    if not config.run['infile']:
        failwith(ER.OPT_MISSING, "option infile required (-i/--infile)")
    else:
        if not os.path.exists(config.run['infile']):
            failwith(ER.OPT_BAD, "infile [%s] does not exist" % config.run['infile'])
        elif not os.path.isfile(config.run['infile']):
            failwith(ER.OPT_BAD, "infile [%s] is not a regular file" % config.run['infile'])

    # Get video ID (MD5 sum by default)
    if config.run['id']:
        vinfo.id = config.run['id']
    elif config.vid['autoid']:
        vinfo.id = util.md5sum(config.run['infile'])
        logthis("MD5 Checksum:", suffix=vinfo.id, loglevel=LL.INFO)

    # Connect to Mongo
    monjer = db.mongo(config.mongo)

    # Build pre-transcode data
    vinfo.vername = config.vid['vername']
    if monjer and vinfo.id:
        if not vinfo.vername:
            failwith(ER.OPT_MISSING, "No version name specified. Use --vername to specify the version name. Aborting.")
        vdata = vdataBuild()
    else:
        logthis("Setting update mode to MXM.NONE", loglevel=LL.DEBUG)
        vinfo.mxmode = MXM.NONE
        vdata = False

    # Perform transcoding
    vvdata = transcode(config.run['infile'], config.run['outfile'])
    if vdata:
        vdata['versions'][vinfo.vername] = vvdata

    # Grab an interesting frame for the screenshot
    if config.run['vscap']:
        vsdata = sscapture(config.run['infile'], config.run['vscap'], vinfo.id)
        if vdata:
            vdata['vscap'] = vsdata

    # Insert data into Mongo
    if vdata:
        vdataInsert(vdata)

    logthis("*** Transcoding task completed successfully.", loglevel=LL.INFO)
    return 0

def sscapture(xconfig, offset, src_id=None):
    """
    Screenshot capture
    """
    infile = xconfig.run['infile']

    # split up infile
    i_real = os.path.realpath(os.path.expanduser(infile))
    i_path, i_file = os.path.split(infile)  # pylint: disable=unused-variable
    i_base, i_ext = os.path.splitext(i_file)  # pylint: disable=unused-variable

    # build filename & path stuffs
    ssout = i_base + '.png'
    ssoutwp = i_base + '.webp'
    ssdir = os.path.realpath(os.path.expanduser(xconfig.vscap['basedir']))  # pylint: disable=unused-variable
    ssdir_full = xconfig.vscap['basedir'] + '/full'
    ssout_full = os.path.realpath(ssdir_full + '/' + ssout)

    if not xconfig.vscap['nothumbs']:
        ssdir_480 = xconfig.vscap['basedir'] + '/480'
        ssdir_240 = xconfig.vscap['basedir'] + '/240'
        ssout_fullwp = os.path.realpath(ssdir_full + '/' + ssoutwp)
        ssout_480 = os.path.realpath(ssdir_480 + '/' + ssout)
        ssout_480wp = os.path.realpath(ssdir_480 + '/' + ssoutwp)
        ssout_240 = os.path.realpath(ssdir_240 + '/' + ssout)
        ssout_240wp = os.path.realpath(ssdir_240 + '/' + ssoutwp)
        ssdir_list = [ssdir_full, ssdir_480, ssdir_240]
    else:
        ssout_fullwp = None
        ssout_480 = None
        ssout_480wp = None
        ssout_240 = None
        ssout_240wp = None
        ssdir_list = [ssdir_full]

    # ensure target dirs exist
    for tpath in ssdir_list:
        if mkdirp(tpath) is True:
            logthis("Target path OK:", suffix=tpath, loglevel=LL.DEBUG)
        else:
            logthis("Failed to create target path:", suffix=tpath, loglevel=LL.ERROR)
            return None

    # grab the frame
    logthis("Capturing frame at offset:", suffix=offset, loglevel=LL.INFO)
    if ffmpeg.vscap(i_real, offset, ssout_full, supout=(loglevel() < LL.DEBUG)) is True:
        logthis("Grabbed frame and saved to", suffix=ssout_full, loglevel=LL.VERBOSE)
    else:
        logthis("ffmpeg run failed, aborting", loglevel=LL.ERROR)
        return None

    if not xconfig.vscap['nothumbs']:
        # scale to smaller versions; convert all versions to WebP
        logthis("Generating intermediate sizes and WebP versions", loglevel=LL.VERBOSE)
        ffmpeg.im_scale(ssout_full, ssout_480, 480)
        ffmpeg.im_scale(ssout_full, ssout_240, 240)
        ffmpeg.webp_convert(ssout_full, ssout_fullwp)
        ffmpeg.webp_convert(ssout_480, ssout_480wp)
        ffmpeg.webp_convert(ssout_240, ssout_240wp)
    else:
        logthis("Skipping intermediate sizes and WebP versions", loglevel=LL.DEBUG)


    logthis("Screenshot generation complete.", ccode=C.GRN, loglevel=LL.INFO)

    # Set vscap vdata
    vsdata = {
                'filename': ssout,
                'basename': i_base,
                'offset': offset,
                'src_id': src_id,
                'sizes': {
                    '240': ssout_240,
                    '240w': ssout_240wp,
                    '480': ssout_480,
                    '480w': ssout_480wp,
                    'full': ssout_full,
                    'fullw': ssout_fullwp
                }
             }

    return vsdata


def transcode(infile, outfile=None):
    """
    Transcode video
    """
    global monjer, config

    # Split apart the input file, path, and extension
    vinfo.infile.full = os.path.realpath(os.path.expanduser(infile))
    vinfo.infile.path, vinfo.infile.file = os.path.split(vinfo.infile.full)
    vinfo.infile.base, vinfo.infile.ext = os.path.splitext(vinfo.infile.file)

    # Get Matroska data
    logthis("Getting Matroska data", loglevel=LL.DEBUG)
    mkv = getMatroska(vinfo.infile.full)

    ## Set up encoding options ##

    ## Subtitles
    if trueifset(config.run['bake'], typematch=True):
        # Set up subtitle baking options (hardsub)
        stracks = mkv['subtitle_tracks']

        # Parse run.bake option for MKV subtitle track number (zero-based; eg. mkvmerge compatible)
        # If run.bake is 'auto' or set to True, use whichever track is marked as default
        if config.xcode['subid'].lower() == 'auto':
            subset = True
        elif config.xcode['subid'] is True:
            subset = True
        else:
            try:
                subset = int(config.xcode['subid'])
            except ValueError as e:
                logthis("Unable to parse track number for xcode.subid (--subid) option:", suffix=e, loglevel=LL.ERROR)
                logthis("Using whichever track is marked as default", loglevel=LL.WARNING)
                subset = True

        if len(stracks) > 1:
            logthis("Multiple subtitle tracks in source container", loglevel=LL.WARNING)

        # Loop through the tracks to find the matching track or default track
        for st in stracks:
            logthis("** Subs: Track %d (%s) - '%s' [%s] %s" % (st['number'] - 1, st['codec_id'], st['name'], st['language'], strifset(st['default'], "***")), loglevel=LL.INFO)
            if st['default']: deftrack = st
            if subset == (st['number'] - 1): vinfo.sub.tdata = st
        # if no track found, use default
        if not vinfo.sub.tdata:
            # throw a warning if our chosen track doesn't exist
            if subset is not True and subset != (deftrack['number'] - 1):
                logthis("Using default subtitle track. Track not found with ID", suffix=subset, loglevel=LL.WARNING)
            vinfo.sub.tdata = deftrack

        # Get important bits of track data
        vinfo.sub.track = vinfo.sub.tdata['number'] - 1
        vinfo.sub.type = vinfo.sub.tdata['codec_id']

        # Set ffmpeg options for subs
        # For ASS subs, dump font attachments
        if vinfo.sub.type == STYPE.ASS:
            logthis("Dumping font attachments...", loglevel=LL.INFO)
            fontlist = ffmpeg.dumpFonts(vinfo.infile.full, config.xcode['fontdir'])
            subfile = "subtrack.ass"
            ffo.subs = ['ass=%s' % subfile]
        elif vinfo.sub.type == STYPE.SRT:
            subfile = "subtrack.srt"
            ffo.subs = ["subtitles=%s:force_style='%s'" % (subfile, config.xcode['srt_style'])]
        else:
            logthis("Unsupported subtitle type:", suffix=vinfo.sub.type, loglevel=LL.ERROR)
            failwith(ER.UNSUPPORTED, "Sub type not supported. Unable to continue. Aborting.")

        # Extract subtitle track
        logthis("Extracting subtitle track from container...", loglevel=LL.INFO)
        ffmpeg.dumpSub(vinfo.infile.full, vinfo.sub.track, subfile)

    ## Audio
    atracks = mkv['audio_tracks']

    if config.xcode['aid']:
        subset = config.xcode['aid']
    else:
        subset = True

    for st in atracks:
        logthis("** Audio: Track %d (%s) - '%s' %dch [%s] %s" % (st['number'] - 1, st['codec_id'], st['name'], st['channels'], st['language'], strifset(st['default'], "***")), loglevel=LL.INFO)
        if st['default']: deftrack = st
        if subset == (st['number'] - 1): vinfo.aud.tdata = st
    # if no track found, use default
    if not vinfo.aud.tdata:
        # throw a warning if our chosen track doesn't exist
        if subset is not True and subset != (deftrack['number'] - 1):
            logthis("Using default audio track. Track not found with ID", suffix=subset, loglevel=LL.WARNING)
        vinfo.aud.tdata = deftrack

    # Get important bits of track data
    vinfo.aud.track = vinfo.aud.tdata['number'] - 1
    vinfo.aud.type = vinfo.aud.tdata['codec_id']
    vinfo.aud.channels = vinfo.aud.tdata['channels']

    # Determine if we need to transcode the audio
    if str(config.xcode['acopy']).lower() == 'auto':
        # stream copy apparently only works for the default track
        if vinfo.aud.type == 'A_AAC' and vinfo.aud.tdata['default']:
            vinfo.aud.copy = True
        else:
            vinfo.aud.copy = False
    elif config.xcode['acopy'] == 1 or config.xcode['acopy'] is True:
        vinfo.aud.copy = True
    else:
        vinfo.aud.copy = False

    # Determine if we need to downmix/upmix
    if config.xcode['downmix'].lower() == 'auto':
        if vinfo.aud.channels != 2:
            vinfo.aud.downmix = True
            # If stream copy is also set to auto, make sure it's
            # disabled if we need to downmix
            if config.xcode['acopy'].lower() == 'auto':
                vinfo.aud.copy = False
        else:
            vinfo.aud.downmix = False
    elif config.xcode['downmix'] == 1 or config.xcode['downmix'] is True:
        vinfo.aud.downmix = True
    else:
        vinfo.aud.downmix = False

    # Set audio encoding options
    if vinfo.aud.copy:
        # stream copy
        ffo.audio += ['-c:a', 'copy']
    else:
        # set codec
        ffo.audio += ['-c:a:%d' % vinfo.aud.track, 'libfaac']
        # set audio bitrate
        ffo.audio += ['-b:a:%d' % vinfo.aud.track, '%dk' % config.xcode['abr']]
        # set downmix (or possibly upmix if mono), if enabled
        if vinfo.aud.downmix: ffo.audio += ['-ac', '2']

    ## Filtering
    if config.xcode['scale']:
        ffo.scaler = ['scale=%s' % config.xcode['scale']]
    if config.xcode['anamorphic']:
        ffo.scaler = ['scale=854:480']
        ffo.video += ['-aspect', '16:9']

    # prefix filters to ffo.video
    if ffo.scaler or ffo.subs:
        ffo.video = ['-vf', ','.join(ffo.scaler + ffo.subs)] + ffo.video

    ## Video & Output filename
    ffo.video += ['-c:v', 'libx264', '-crf', str(config.xcode['crf']), '-preset:v', config.xcode['libx264_preset']]

    # Get output path
    if outfile and os.path.isdir(outfile):
        vinfo.outfile.path = os.path.realpath(os.path.expanduser(outfile))
    else:
        vinfo.outfile.path = os.path.realpath('.')

    # Select output container & extension
    if not config.xcode['flv']:
        ffo.video += ['-movflags', '+faststart']
        vinfo.outfile.ext = '.mp4'
    else:
        vinfo.outfile.ext = '.flv'

    # Get output filename
    if outfile and not os.path.isdir(outfile):
        vinfo.outfile.path, vinfo.outfile.file = os.path.split(os.path.realpath(os.path.expanduser(outfile)))
        vinfo.outfile.base, vinfo.outfile.ext = os.path.split(vinfo.outfile.file)
    else:
        vinfo.outfile.base = vinfo.infile.base

    # Outfile realpath
    vinfo.outfile.full = vinfo.outfile.path + '/' + vinfo.outfile.base + vinfo.outfile.ext
    vinfo.outfile.file = os.path.split(vinfo.outfile.full)[1]


    logthis("-- Using Subtitle Track:", suffix=vinfo.sub.track, loglevel=LL.INFO)
    logthis("-- Using Audio Track:", suffix=vinfo.aud.track, loglevel=LL.INFO)
    logthis("-- Output filename:", suffix=vinfo.outfile.full, loglevel=LL.INFO)

    ## Build ffmpeg command
    ffoptions = ['-y', '-i', vinfo.infile.full] + ffo.video + ffo.audio + [vinfo.outfile.full]
    ffmpeg.run(ffoptions, (not config.xcode['show_ffmpeg']))

    ## Cleanup
    if trueifset(config.run['bake'], typematch=True):
        logthis("Removing font and subtitle files...", loglevel=LL.VERBOSE)
        try:
            os.remove(subfile)
        except Exception as e:
            logexc(e, "Unable to remove subfile")

        if not config.xcode['fontsave']:
            for ff in fontlist:
                if config.xcode['fontdir']:
                    try:
                        os.remove(os.path.expanduser(config.xcode['fontdir']).rstrip('/') + "/" + ff)
                    except Exception as e:
                        logexc(e, "Unable to remove font from fontdir (%s)" % (ff))
                else:
                    try:
                        os.remove(ff)
                    except Exception as e:
                        logexc(e, "Unable to remove font (%s)" % (ff))

    logthis("Transcoding complete", ccode=C.GRN, loglevel=LL.INFO)

    if vinfo.vername:
        vvdata = {
                    'encoder': {'encode': ' '.join(ffoptions)},
                    'mediainfo': util.mediainfo(vinfo.outfile.full, config),
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

    logthis("Inserting data into Mongo...", loglevel=LL.INFO)
    if vinfo.mxmode == MXM.INSERT:
        monjer.insert('videos', xvid)
    elif vinfo.mxmode == MXM.UPDATE:
        vsetter = {'versions.'+vinfo.vername : xvid['versions'][vinfo.vername]}
        monjer.update_set('videos', vinfo.id, vsetter)


def vdataBuild():
    """
    Query MongoDB and build data structures prior to transcoding
    """
    global monjer, config

    vx.fdi = monjer.findOne('files', {'_id': vinfo.id})
    if vx.fdi:
        logthis("Found matching entry in database", loglevel=LL.INFO)
        # Get episode information
        if vx.fdi['episode_id']:
            vx.fdi_epx = monjer.findOne('episodes', {'_id': vx.fdi['episode_id']})
            logthis("Found matching episode entry", loglevel=LL.VERBOSE)
        else:
            vx.fdi_epx = None

        # Get series information
        if vx.fdi['series_id']:
            vx.fdi_srx = monjer.findOne('series', {'_id': vx.fdi['series_id']})
            logthis("Found matching series entry", loglevel=LL.VERBOSE)
        else:
            vx.fdi_srx = None

        # Check if matching video already exists
        if not monjer.findOne('videos', {'_id': vx.fdi['_id']}):
            logthis("Entry does not already exist. Populating video metadata", loglevel=LL.INFO)
            vinfo.mxmode = MXM.INSERT
            # Check location
            if config.vid['location']:
                # Get from running config (--vername option or vid.vername)
                vinfo.location = config.vid['location']
            else:
                # Otherwise, get first location from list
                vinfo.location = vx.fdi['location'].keys()[0]

            # Initialize metadata
            xvid = {
                    '_id': vx.fdi['_id'],
                    'metadata': {
                            'title': setifset(vx.fdi_epx, 'EpisodeName'),
                            'series': vx.fdi['fparse']['series'],
                            'episode': vx.fdi['fparse']['episode'],
                            'season': vx.fdi['fparse']['season'],
                            'special': vx.fdi['fparse']['special']
                        },
                    'tdex_id': setifset(vx.fdi_srx, 'norm_id'),
                    'series_id': vx.fdi['series_id'],
                    'episode_id': vx.fdi['episode_id'],
                    'tvdb_id': {'series': vx.fdi_srx['xrefs']['tvdb'], 'episode': vx.fdi_epx['tvdb_id']},
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
                            'enabled': trueifset(config.run['bake'], typematch=True),
                            'lang': 'eng',
                            'fansub': setifset(config.run, 'fansub')
                        },
                    'versions': {}
                   }
        else:
            # Entry already exists in db.videos
            logthis("Entry already exists. Will update version or vscap information.", loglevel=LL.INFO)
            vinfo.mxmode = MXM.UPDATE
            xvid = {'versions': {}}
    else:
        logthis("No matching entry found in database. ID:", suffix=vinfo.id, loglevel=LL.ERROR)
        failwith(ER.NOTFOUND, "No match for VID. Will not contiue. Aborting.")

    return xvid

def getMatroska(vfile):
    """
    Get metadata and track information from Matroska containers
    """
    try:
        with open(vfile) as f: mkv = enzyme.MKV(f)
    except enzyme.MalformedMKVError as e:
        logexc(e, "Not a Matroska container or segment is corrupt")
        return False
    return mkv.to_dict()


def setifset(idict, ikey):
    """return value from @idict if it exists, otherwise None"""
    if ikey in idict:
        return idict[ikey]
    else:
        return False

def trueifset(xeval, typematch=False):
    """return True if @xeval is set, otherwise False"""
    if typematch:
        if not (xeval is False or xeval is None): return True
        else: return False
    else:
        if xeval: return True
        else: return False

def strifset(xeval, iftrue, iffalse="", typematch=False):
    """return @iftrue if statement True, otherwise return @iffalse"""
    if typematch:
        if not (xeval is False or xeval is None): return iftrue
        else: return iffalse
    else:
        if xeval: return iftrue
        else: return iffalse
