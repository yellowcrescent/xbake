#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.ascan
Audio/Music Scanner

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2016-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import os
import re
import socket
import time
import multiprocessing
import mimetypes
from urlparse import urlparse

import mutagen
import taglib
import arrow
from setproctitle import setproctitle

from xbake import __version__, __date__
from xbake.common.logthis import *
from xbake.mscan import util, out
from xbake.mscan.mscan import (clean_overrides, check_overrides, parse_overrides,
                               parse_xattr_overrides, filter_fname)

# File extension filter
fext = re.compile(r'\.(mp3|m4a|flac|ape|wma|aac|ogg|vob|wv|wav|wmf)', re.I)

config = None

def run(xconfig):
    """
    Implements --ascan mode
    """
    global config
    config = xconfig

    # Check input filename
    if not config.run['infile']:
        failwith(ER.OPT_MISSING, "option infile required (-i/--infile)")
    else:
        if not os.path.exists(config.run['infile']):
            failwith(ER.OPT_BAD, "path/file [%s] does not exist" % (config.run['infile']))
        if config.run['single'] and not os.path.isfile(config.run['infile']):
            failwith(ER.OPT_BAD, "file [%s] is not a regular file; --single mode is used when scanning only one file" % (config.run['infile']))
        elif not config.run['single'] and not os.path.isdir(config.run['infile']):
            failwith(ER.OPT_BAD, "file [%s] is not a directory; use --single mode if scanning only one file" % (config.run['infile']))

    # Examine and enumerate files
    if config.run['single']:
        new_files, flist = scan_single(config.run['infile'], config.scan['mforce'])  # pylint: disable=unused-variable
    else:
        if config.run['tsukimi'] is True:
            tstatus('scanlist', scanlist=get_scanlist(config.run['infile'], config.scan['follow_symlinks']))
        new_files, flist = scan_dir(config.run['infile'], config.scan['follow_symlinks'],
                                    config.scan['mforce'], int(config.scan['procs']))

    # Build host data
    hdata = {
                'hostname': socket.getfqdn(),
                'tstamp': time.time(),
                'duration': 0, # FIXME
                'topmost': os.path.realpath(config.run['infile']),
                'command': ' '.join(sys.argv),
                'version': __version__
            }

    # Build main output structure
    odata = {
                'scan': hdata,
                'files': flist
            }

    # Parse outfile
    if not config.run['outfile']:
        config.run['outfile'] = config.scan['output']

    # If no file defined, or '-', write to stdout
    if not config.run['outfile'] or config.run['outfile'] == '-':
        config.run['outfile'] = '/dev/stdout'

    # Parse URLs
    ofp = urlparse(config.run['outfile'])

    tstatus('output', event='start', output=config.run['outfile'])
    if ofp.scheme == 'mongodb':
        # Write to Mongo
        logthis(">> Output driver: Mongo", loglevel=LL.VERBOSE)
        if ofp.hostname is None:
            cmon = config.mongo
            logthis("Using existing MongoDB configuration; URI:", suffix=cmon['uri'], loglevel=LL.DEBUG)
        else:
            cmon = {'uri': config.run['outfile']}
            logthis("Using new MongoDB URI:", suffix=cmon['uri'], loglevel=LL.DEBUG)
        ostatus = out.to_mongo(odata, cmon)
    elif ofp.scheme == 'http' or ofp.scheme == 'https':
        # Send via HTTP(S) to a listening XBake daemon, or other web service
        logthis(">> Output driver: HTTP/HTTPS", loglevel=LL.VERBOSE)
        ostatus = out.to_server(odata, config.run['outfile'], config)
    else:
        # Write to file or stdout
        logthis(">> Output driver: File", loglevel=LL.VERBOSE)
        ostatus = out.to_file(odata, ofp.path)

    if ostatus['status'] == "ok":
        logthis("*** Scanning task completed successfully.", loglevel=LL.INFO)
        tstatus('complete', status='ok', files=len(flist))
        return 0
    elif ostatus['status'] == "warning":
        logthis("*** Scanning task completed, with warnings.", loglevel=LL.WARNING)
        tstatus('complete', status='warning')
        return 49
    else:
        logthis("*** Scanning task failed.", loglevel=LL.ERROR)
        tstatus('complete', status='fail')
        return 50

    return 0


def scan_single(infile, mforce=False):
    """
    Scan a single file
    """
    ddex = {}
    new_files = 0

    # Parse overrides for directory the file is in
    tdir = os.path.dirname(os.path.realpath(infile))
    ovrx = parse_xattr_overrides(tdir)
    ovrx.update(parse_overrides(tdir))
    ovrx = clean_overrides(ovrx)

    dasc = scanfile(infile, ovrx=ovrx, mforce=mforce)
    if dasc:
        ddex[infile] = dasc
        new_files += 1

    return (new_files, ddex)


def get_scanlist(dpath, dreflinks=True):
    """
    Return a list of files to be scanned by scan_dir()
    """
    dryout = scan_dir(dpath, dreflinks, dryrun=True)[1]
    return dryout.values()


def scan_dir(dpath, dreflinks=True, mforce=False, procs=0, dryrun=False):
    """
    Scan a directory recursively; follows symlinks by default
    """
    ddex = {}
    new_files = 0

    if dryrun is False:
        ## Set up workers and IPC
        if procs == 0:
            procs = multiprocessing.cpu_count()
        mp_inq = multiprocessing.Queue()
        mp_outq = multiprocessing.Queue()

        ## Start queue runners
        wlist = []
        for wid in range(procs): # pylint: disable=unused-variable
            cworker = multiprocessing.Process(name="xbake: scanrunner", target=scanrunner, args=(mp_inq, mp_outq))
            wlist.append(cworker)
            cworker.start()

    ## Enumerate files
    for tdir, dlist, flist in os.walk(unicode(dpath), followlinks=dreflinks):  # pylint: disable=unused-variable
        # get base & parent dir names
        tdir_base = os.path.split(tdir)[1]  # pylint: disable=unused-variable
        tdir_parent = os.path.split(os.path.split(tdir)[0])[1]  # pylint: disable=unused-variable
        ovrx = {}

        # Get xattribs
        ovrx = parse_xattr_overrides(tdir)

        # Check if ignore flag is set for this directory (xattribs only)
        if ovrx.has_key('ignore'):
            logthis("Skipping directory, has 'ignore' flag set in xattribs:", suffix=tdir, loglevel=LL.INFO)
            continue

        # Parse overrides for this directory
        ovrx.update(parse_overrides(tdir))

        if dryrun is False:
            logthis("*** Scanning files in directory:", suffix=tdir, loglevel=LL.INFO)

        # enum files in this directory
        for xv in flist:
            xvreal = os.path.realpath(unicode(tdir + '/' + xv))
            xvbase, xvext = os.path.splitext(xv)  # pylint: disable=unused-variable

            # Skip .xbake file
            if unicode(xv) == unicode('.xbake'): continue

            # Skip unsupported filetypes, non-regular files, and broken symlinks
            if not os.path.exists(xvreal):
                logthis("Skipping broken symlink:", suffix=xvreal, loglevel=LL.WARNING)
                continue
            if not os.path.isfile(xvreal):
                logthis("Skipping non-regular file:", suffix=xvreal, loglevel=LL.VERBOSE)
                continue
            if not fext.match(xvext):
                logthis("Skipping file with unsupported extension:", suffix=xvreal, loglevel=LL.DEBUG)
                continue

            # Skip file if on the overrides 'ignore' list
            if check_overrides(ovrx, xv):
                logthis("Skipping file. Matched rule in override ignore list:", suffix=xvreal, loglevel=LL.INFO)
                continue

            # Create copy of override object and strip-out unneeded values and flags
            ovrx_sub = clean_overrides(ovrx)

            # Get file properties
            if dryrun is True:
                ddex[new_files] = os.path.realpath(tdir + '/' + xv)
                new_files += 1
            else:
                mp_inq.put({'infile': xvreal, 'ovrx': ovrx_sub, 'mforce': mforce})

    ## Tend the workers
    if dryrun is False:
        # Pump terminators at the end of the queue
        for wid in range(procs):
            mp_inq.put({'EOF': True})

        # Monitor scanrunner progress
        logthis("File enumeration complete. Waiting for scanrunner to complete...", loglevel=LL.DEBUG)
        while len(wlist) > 0:
            # pull scan data off the outbound queue
            for tk in range(mp_outq.qsize()):  # pylint: disable=unused-variable
                try:
                    xfile, xdata = mp_outq.get(block=False)
                    logthis("got file from queue:", suffix=xfile, loglevel=LL.DEBUG)
                    ddex[xfile] = xdata
                    new_files += 1
                except:
                    pass

            # check to see if the kids have died yet
            for wk, wid in enumerate(wlist):
                if not wid.is_alive():
                    logthis("Scanrunner is complete; pid =", suffix=wid.pid, loglevel=LL.DEBUG)
                    del(wlist[wk])
                    break

    return (new_files, ddex)


def scanrunner(in_q, out_q):
    """
    Process queue runner
    """
    hproc = multiprocessing.current_process()
    setproctitle("xbake: scanrunner")
    while True:
        # pop next job off the queue; will block until a job is available
        thisjob = in_q.get()
        if thisjob.get('EOF') is not None:
            logthis("Got end-of-queue marker; terminating; pid =", suffix=hproc.pid, loglevel=LL.DEBUG)
            # we need to wait until the master process pulls our items from the queue
            while out_q.qsize() > 0:
                time.sleep(0.1)
            os._exit(0)
        scandata = scanfile(**thisjob)
        if scandata is not None:
            out_q.put((thisjob['infile'], scandata))


def scanfile(infile, ovrx={}, mforce=False):
    """
    Read audio file attributes, tags, and metadata for @infile
    """
    dasc = {}

    # get file parts
    xvreal = infile
    tdir, xv = os.path.split(xvreal)
    xvbase, xvext = os.path.splitext(xv)

    # get base & parent dir names
    tdir_base = os.path.split(tdir)[1]
    tdir_parent = os.path.split(os.path.split(tdir)[0])[1]

    logthis("Examining file:", suffix=xv, loglevel=LL.INFO)
    tstatus('scanfile', event='start', filename=xv)

    # Get xattribs
    fovr = {}
    fovr.update(ovrx)
    fovr.update(parse_xattr_overrides(xvreal))
    if 'ignore' in fovr:
        logthis("File has 'ignore' flag set via override; skipping", loglevel=LL.INFO)
        return None

    # Get file path information
    dasc['dpath'] = {'base': tdir_base, 'parent': tdir_parent, 'full': tdir}
    dasc['fpath'] = {'real': xvreal, 'base': xvbase, 'file': xv, 'ext': xvext.replace('.', '')}

    # Stat, Extended Attribs, Ownership
    dasc['stat'] = util.dstat(xvreal)
    dasc['owner'] = {'user': util.getuser(dasc['stat']['uid']), 'group': util.getgroup(dasc['stat']['gid'])}

    # Modification key (MD5 of inode number + mtime + filesize)
    mkey_id = util.getmkey(dasc['stat'])
    dasc['mkey_id'] = mkey_id
    dasc['status'] = 'new'

    # Get mediainfo & build codec string
    minfo = util.mediainfo(xvreal, config, format_lower=False)
    if minfo['audio'][0]['format'] == "mpeg audio":
        if minfo['audio'][0]['format'].endswith('3'):
            acodec = "MP3"
        elif minfo['audio'][0]['format'].endswith('2'):
            acodec = "MP2"
        else:
            acodec = "MPEG Audio"
            if 'format_profile' in minfo['audio'][0]:
                acodec += " " + minfo['audio'][0]['format_profile']
    else:
        acodec = ""
        if minfo['general']['format'] != minfo['audio'][0]['format']:
            acodec = minfo['general']['format'] + " "
        acodec += minfo['audio'][0]['format']
        if 'format_profile' in minfo['audio'][0]:
            acodec += " " + minfo['audio'][0]['format_profile']

    if 'bit_depth' in minfo['audio'][0]:
        bitdepth = minfo['audio'][0]['bit_depth']
    else:
        bitdepth = 16

    # Open file with Mutagen
    try:
        mf = mutagen.File(xvreal)
    except OSError as e:
        logexc(e, "Failed to open file")
        return None
    except Exception as e:
        logexc(e, "Failed to parse tag data from file")
        return None

    # Determine MIME type
    try:
        amime = mf.mime[0]
    except:
        try:
            amime = mimetypes.guess_type(xvreal)[0]
        except:
            amime = None

    if amime is None:
        logthis("Failed to auto-detect MIME type for file:", suffix=xvreal, loglevel=LL.WARNING)
        amime = "audio/x-" + xvext.lower()
    logthis("Detected MIME-Type:", suffix=amime, loglevel=LL.DEBUG)

    tags = mf.tags
    tdate = parse_album_date(tags)
    if tdate is not None:
        tyear = tdate.format("YYYY")
        tstamp = tdate.timestamp
    else:
        tyear = None
        tstamp = None

    dasc['subsong'] = {
                        'index': None,
                        'start_time': None,
                        'duration': None,
                        'cue': None
                      }
    dasc['tags'] = {
                        'artist': get_best_tag(tags, ('ARTIST', 'TPE1', 'TOPE', 'Author')),
                        'album': get_best_tag(tags, ('ALBUM', 'TALB', 'TOAL', 'WM/AlbumTitle')),
                        'title': get_best_tag(tags, ('TITLE', 'TIT2', 'TIT3', 'Title')),
                        'year': tyear,
                        'timestamp': tstamp,
                        'genre': get_best_tag(tags, ('GENRE', 'TCON', 'WM/Genre')),
                        'tracknum': parse_tracknum(tags, forceInt=True),
                        'trackstr': parse_tracknum(tags, forceInt=False),
                        'disc': get_best_tag(tags, ('DISCNUMBER', 'DISC', 'TPOS')),
                        'album_artist': get_best_tag(tags, ('ALBUMARTIST', 'TXXX:ALBUM ARTIST', 'TXXX:ALBUM_ARTIST', 'WM/AlbumArtist'))
                   }
    dasc['alltags'] = get_all_tags_once(tags)
    dasc['format'] = {
                        'format': acodec,
                        'mime': amime,
                        'channels': mf.info.channels,
                        'sampling_rate': mf.info.sample_rate,
                        'encoding_settings': minfo['audio'][0].get('encoding_settings'),
                        'writing_library': minfo['audio'][0].get('writing_library'),
                        'bitrate': mf.info.bitrate,
                        'bit_depth': bitdepth,
                        'length': mf.info.length
                     }


    if dasc['tags']['album_artist'] is None:
        dasc['tags']['album_artist'] = dasc['tags']['artist']

    logthis(u"Title: {title} / Track: {tracknum} ({trackstr}) / Artist: {artist} / Album: {album} / AlbumArtist: {album_artist} / Year: {year}".format(**dasc['tags']), loglevel=LL.DEBUG)


    # Record last time this entry was updated (UTC)
    last_up = arrow.utcnow().timestamp
    logthis("last_updated =", suffix=last_up, loglevel=LL.DEBUG)
    dasc['last_updated'] = last_up

    return dasc

def get_true_value(inval):
    """return the true value from any object that might be in the way"""
    if isinstance(inval, unicode) or isinstance(inval, str) or isinstance(inval, int):
        realval = inval
    elif isinstance(inval, mutagen.id3._specs.ID3TimeStamp):
        realval = unicode(inval)
    else:
        try:
            realval = inval.value
        except:
            logthis("Error determining true value for <%s>" % (type(inval)), suffix=inval, loglevel=LL.WARNING)
            realval = None
    return realval

def get_all_tags_once(tagdata):
    """return a dict of all tags containing their first value"""
    tout = {}
    for ttag, tval in dict(tagdata).items():
        try:
            tout[ttag] = get_true_value(tval[0])
        except Exception as e:
            logexc(e, "Failed to convert %s tag for serialization" % (ttag))
    return tout

def get_single_tag(tagdata, tagname):
    """return first tag in tagdata matching name; else, return None"""
    tg = tagdata.get(tagname)
    if tg is None:
        return None
    else:
        try:
            tout = get_true_value(tg[0])
            if isinstance(tout, unicode) or isinstance(tout, str):
                return tout.strip()
            else:
                return tout
        except:
            logthis("Encountered null tag data for", suffix=tagname, loglevel=LL.WARNING)
            return None

def get_best_tag(tagdata, taglist, cast=None, strict=True):
    """
    return a single value from a list of candidate tags, @taglist
    @cast should be a type, such as str, int, float, etc. or None
    if @strict is True, then None will be returned if the type conversion fails
    otherwise the raw, unconverted value is returned
    """
    ctag = None
    rawval = None
    for ttag in tuple(taglist):
        if ttag in tagdata:
            try:
                rawval = get_true_value(tagdata.get(ttag)[0])
                ctag = ttag
                break
            except:
                logthis("Encountered null tag data for", suffix=ttag, loglevel=LL.WARNING)
                continue

    if cast is not None:
        try:
            outval = cast(rawval)
        except:
            if strict is True:
                outval = None
            else:
                outval = rawval
    else:
        outval = rawval

    if ctag is not None:
        logthis("%s => " % (ctag), suffix=outval, loglevel=LL.DEBUG2)
    else:
        logthis("No match for (%s)" % ("/".join(tuple(taglist))), loglevel=LL.DEBUG)

    return outval

def parse_album_date(tagdata):
    """parse various datetime formats and return an Arrow date object"""
    ad = None
    for dt in ('TDRC', 'TDAT', 'TYER', 'TRDA', 'DATE', 'YEAR', 'WM/Year'):
        if dt in tagdata:
            try:
                tstr = get_true_value(tagdata[dt][0])
                ad = arrow.get(tstr, ["YYYY-MM-DD", "YYYY"])
                break
            except:
                logthis("Failed to parse tag:", prefix=dt, suffix=tstr, loglevel=LL.WARNING)
    return ad

def parse_tracknum(tagdata, forceInt=False):
    """parse track number from tag data and output a normalized value"""
    traw = get_best_tag(tagdata, ('TRACKNUMBER', 'TRCK', 'WM/TrackNumber'))
    ttxt = None
    tnum = None
    try:
        ttxt = re.match(r'^([0-9]+)', traw).group(1)
        tnum = int(ttxt)
    except:
        if forceInt is False:
            if ttxt is not None:
                tnum = ttxt
    return tnum


def parse_cue_file(rpath):
    """parse CUE sheet"""
    pass
