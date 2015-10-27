#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# mscan - xbake/mscan/mscan.py
# XBake: Media scanner
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
import subprocess
import distance
from urlparse import urlparse

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith
from xbake.common.logthis import print_r

from xbake.xcode import ffmpeg
from xbake.mscan import util
from xbake.mscan import out
from xbake.common import db
from xbake.common import fsutil

from xbake.mscan import mdb
from xbake.mscan.mdb import MCMP

class DSTS:
    NEW = 'new'
    UNCHANGED = 'unchanged'
    RENAMED = 'renamed'

class CONM:
    FILE    = 1
    MLOCAL  = 2
    MREMOTE = 3
    APIREM  = 4

# File match regexes
fregex = [
            "^(\[[^\]]+\])[\s._]*(?P<series>.+?)(?:[\s._]-[\s._]|[\._])(?:(?P<special>(NCOP|NCED|OP|ED|PV|OVA|ONA|Special|Insert|Preview|Lite|Short)\s*-?\s*[0-9]{0,2})|(?:[eEpP]{2}[\s._]*)?(?P<epnum>[0-9]{1,3}))(?P<version>[vep]{1,2}[0-9]{1,2}([-,][0-9]{1,2})?)?",
            "^(?P<series>.+?)(?P<season>[0-9]{1,2})x(?P<epnum>[0-9]{1,2})(.*)$",
            "^(?P<series>.+)[\.\-_ ]SE?(?P<season>[0-9]{1,2})EP?(?P<epnum>[0-9]{1,2})(?:[\.\-_ ](?P<eptitle>.+?))?[\.\-_\[\( ]+(?:([0-9]{3,4}p|web|aac|bd|tv|hd|x?264)+)",
            "^(?P<series>.+)[\._](?P<epnum>[0-9]{1,4})[\._](.*)$",
            "^(?P<series>.+?)[\-_ ](?P<epnum>[0-9]{2})[\-_ ](.*)$",
            "^(?P<series>.+)[sS](?P<season>[0-9]{1,2}) ?[eE](?P<epnum>[0-9]{1,2})(.*)$",
            "^(?P<series>.+?) (?P<season>[0-9]{1,2}) (?P<epnum>[0-9]{1,2}) (.*)$",
            "^(?P<series>.+) - (?P<epnum>[0-9]{1,2})(.*)$",
            "^(?P<series>.+?)(?P<epnum>[0-9]{1,4})\.(.+)$",
            "^(?P<series>.+?)(?P<epnum>[0-9]{2,3})(.+)$",
            "^(?P<epnum>[0-9]{2,4})(.+)$"
         ]

# File extension filter
fext = re.compile('\.(avi|mkv|mpg|mpeg|wmv|vp8|ogm|mp4|mpv)',re.I)

def run(infile,outfile=False,conmode=CONM.FILE,dreflinks=True,**kwargs):
    """
    Implements --scan mode
    """
    global monjer
    conf = __main__.xsetup.config

    # Check input filename
    if not infile:
        failwith(ER.OPT_MISSING, "option infile required (-i/--infile)")
    else:
        if not os.path.exists(infile):
            failwith(ER.OPT_BAD, "path/file [%s] does not exist" % (infile))
        if conf['run']['single'] and not os.path.isfile(infile):
            failwith(ER.OPT_BAD, "file [%s] is not a regular file; --single mode is used when scanning only one file" % (infile))
        elif not conf['run']['single'] and not os.path.isdir(infile):
            failwith(ER.OPT_BAD, "file [%s] is not a directory; use --single mode if scanning only one file" % (infile))

    # Examine and enumerate files
    if conf['run']['single']:
        new_files,flist = scan_single(infile,conf['scan']['mforce'],conf['scan']['nochecksum'],conf['scan']['savechecksum'])
    else:
        new_files,flist = scan_dir(infile,dreflinks,conf['scan']['mforce'],conf['scan']['nochecksum'],conf['scan']['savechecksum'])

    # Scrape for series information
    if new_files > 0:
        mdb.series_scrape()

    # Build host data
    hdata = {
                'hostname': socket.getfqdn(),
                'tstamp': time.time(),
                'duration': 0, # FIXME
                'topmost': os.path.realpath(infile),
                'command': ' '.join(sys.argv),
                'version': __main__.xsetup.version
            }

    # Build main output structure
    odata = {
                'scan': hdata,
                'files': flist,
                'series': mdb.get_tdex()
            }

    # Parse outfile
    if not outfile:
        outfile = conf['scan']['output']

    # If no file defined, or '-', write to stdout
    if not outfile or outfile == '-':
        outfile = '/dev/stdout'

    # Parse URLs
    ofp = urlparse(outfile)

    if ofp.scheme == 'mongo':
        # Write to Mongo
        logthis(">> Output driver: Mongo",loglevel=LL.VERBOSE)
        cmon = conf['mongo']
        if ofp.hostname: cmon['hostname'] = ofp.hostname
        if ofp.port: cmon['port'] = ofp.port
        if ofp.path:
            cmon['database'] = ofp.path.split('/')[1]
            if not cmon['database']: cmon['database'] = conf['mongo']['database']
        out.to_mongo(odata,cmon)
    else:
        # Write to file or stdout
        logthis(">> Output driver: File",loglevel=LL.VERBOSE)
        out.to_file(odata,ofp.path)

    logthis("*** Scanning task completed successfully.",loglevel=LL.INFO)


def scan_dir(dpath,dreflinks=True,mforce=False,nochecksum=False,savechecksum=True):
    """
    Scan a directory recursively; follows symlinks by default
    """

    ddex = {}
    new_files = 0

    for tdir,dlist,flist in os.walk(unicode(dpath),followlinks=dreflinks):
        # get base & parent dir names
        tdir_base = os.path.split(tdir)[1]
        tdir_parent = os.path.split(os.path.split(tdir)[0])[1]
        ovrx = {}

        # Get xattribs
        ovrx = parse_xattr_overrides(tdir)

        # Parse overrides for this directory
        ovrx.update(parse_overrides(tdir))

        logthis("*** Scanning files in directory:",suffix=tdir,loglevel=LL.INFO)

        # enum files in this directory
        for xv in flist:
            xvreal = os.path.realpath(unicode(tdir + '/' + xv))
            xvbase,xvext = os.path.splitext(xv)

            # Skip .xbake file
            if unicode(xv) == unicode('.xbake'): continue

            # Skip unsupported filetypes, non-regular files, and broken symlinks
            if not os.path.exists(xvreal):
                logthis("Skipping broken symlink:",suffix=xvreal,loglevel=LL.WARNING)
                continue
            if not os.path.isfile(xvreal):
                logthis("Skipping non-regular file:",suffix=xvreal,loglevel=LL.VERBOSE)
                continue
            if not fext.match(xvext):
                logthis("Skipping file with unsupported extension:",suffix=xvreal,loglevel=LL.DEBUG)
                continue

            # Skip file if on the overrides 'ignore' list
            if check_overrides(ovrx, xv):
                logthis("Skipping file. Matched rule in override ignore list:",suffix=cfile,loglevel=LL.INFO)
                continue

            # Get file properties
            dasc = scanfile(xvreal,ovrx,mforce,nochecksum)
            if dasc:
                ddex[xv] = dasc
                new_files += 1

    return (new_files,ddex)


def scan_single(dfile,mforce=False,nochecksum=False,savechecksum=True):
    """
    Scan a single media file
    """
    ddex = {}
    new_files = 0
    dasc = scanfile(dfile,mforce=mforce,nochecksum=nochecksum,savechecksum=savechecksum)
    if dasc:
        ddex[dfile] = dasc
        new_files += 1

    return (new_files,ddex)


def scanfile(rfile,ovrx={},mforce=False,nochecksum=False,savechecksum=True):
    """
    Examine file: obtain filesystem stats, checksum, ownership; file/path are parsed
    and episode number, season, and series title extracted; file examined with
    mediainfo and container, video, audio, subtitle track info, and chapter data extracted
    """
    dasc = {}

    # get file parts
    xvreal = rfile
    tdir,xv = os.path.split(xvreal)
    xvbase,xvext = os.path.splitext(xv)

    # get base & parent dir names
    tdir_base = os.path.split(tdir)[1]
    tdir_parent = os.path.split(os.path.split(tdir)[0])[1]

    logthis("Examining file:",suffix=xv,loglevel=LL.INFO)

    # Get xattribs
    fovr = ovrx
    fovr.update(parse_xattr_overrides(xvreal))
    if fovr.has_key('ignore'):
        logthis("File has 'ignore' flag set via override; skipping",loglevel=LL.INFO)
        return False

    # Get file path information
    dasc['dpath'] = { 'base': tdir_base, 'parent': tdir_parent, 'full': tdir }
    dasc['fpath'] = { 'real': xvreal, 'base': xvbase, 'file': xv, 'ext': xvext.replace('.','') }

    # Stat, Extended Attribs, Ownership
    dasc['stat'] = util.dstat(xvreal)
    dasc['owner'] = { 'user': util.getuser(dasc['stat']['uid']), 'group': util.getgroup(dasc['stat']['gid']) }
    # TODO: get xattribs

    # Modification key (MD5 of inode number + mtime + filesize)
    mkey_id = util.getmkey(dasc['stat'])
    dasc['mkey_id'] = mkey_id

    # Determine file status (new, unchanged, or file unchanged but moved/renamed)
    xzist = mdb.mkey_match(mkey_id,xvreal)
    if xzist == MCMP.RENAMED:
        xstatus = DSTS.RENAMED
    elif xzist == MCMP.NOCHG:
        xstatus = DSTS.UNCHANGED
    else:
        xstatus = DSTS.NEW

    dasc['status'] = xstatus

    # Check status and carry on as needed
    if xstatus == DSTS.UNCHANGED:
        logthis("File unchanged:",suffix=xv,loglevel=LL.INFO)
        if mforce:
            logthis("File unchanged, but scan forced. Flag --mforce in effect.",loglevel=LL.WARNING)
        else:
            return False

    # Retrieve or caclulate checksums
    if fovr.has_key('md5') and fovr.has_key('ed2k') and fovr.has_key('crc32'):
        dasc['checksum'] = { 'md5': fovr['md5'], 'ed2k': fovr['ed2k'], 'crc32': fovr['crc32'] }
        logthis("Using checksum information from extended file attributes",loglevel=LL.VERBOSE)
    else:
        if not nochecksum:
            logthis("Calculating checksum...",loglevel=LL.INFO)
            dasc['checksum'] = util.checksum(xvreal)
            if savechecksum:
                save_checksums(xvreal, dasc['checksum'])

    # Get mediainfo
    dasc['mediainfo'] = util.mediainfo(xvreal)

    # Determine series information from path and filename
    dasc['fparse'],dasc['tdex_id'] = parse_episode_filename(dasc,fovr)

    return dasc


def parse_episode_filename(dasc,ovrx={},single=False,longep=False):
    """
    Determines series name, season, episode, and special release data from
    episode filenames and directory path. Outputs the data as the 'fparse' array.
    """
    fparse = { 'series': None, 'season': None, 'episode': None, 'special': None }
    tdex_id = None
    dval = dasc['fpath']['base']

    # Regex matching rounds
    for rgx in fregex:
        logthis("Trying regex:",suffix=rgx,loglevel=LL.DEBUG2)
        mm = re.search(rgx, dval, re.I)
        if mm:
            mm = mm.groupdict()
            # determine series name
            if mm.has_key('series'):
                if not single:
                    ldist = distance.nlevenshtein(dasc['dpath']['base'].lower(), mm['series'].lower())
                    if ldist < 0.26:
                        sser = dasc['dpath']['base']
                        logthis("Using directory name for series name (ldist = %0.3f)" % (ldist),loglevel=LL.DEBUG)
                    else:
                        sser = filter_fname(mm['series'])
                        logthis("Using series name extracted from filename (ldist = %0.3f)" % (ldist),loglevel=LL.DEBUG)
                else:
                    sser = filter_fname(mm['series'])
                    logthis("Using series name extracted from filename",loglevel=LL.DEBUG)
            else:
                # Check base directory name; if it has the season number or season name
                sspc = re.match('(season|s)\s*(?P<season>[0-9]{1,2})', dasc['dpath']['base'], re.I)
                if sspc:
                    # Grab series name from the parent directory; tuck the season number away for later
                    sspc = sspc.groupdict()
                    mm['season'] = sspc['season']
                    sser = dasc['dpath']['parent']
                else:
                    # Directory name should be series name (if you name your directories properly!)
                    sser = dasc['dpath']['base']

            # Grab season name from parsed filename; if it doesn't exist, assume Season 1
            snum = mm.get('season','1')
            if snum is None: snum = '1'

            # Get episode number
            epnum = mm.get('epnum','0')
            if epnum is None: epnum = '0'

            # Fix episode number, if necessary
            if not longep:
                if int(epnum) > 100:
                    # For numbers over 100, assume SSEE encoding
                    # (ex: 103 = Season 1, Episode 3)
                    epnum = int(mm['epnum'][-2:])
                    snum  = int(mm['epnum'][:(len(mm['epnum']) -2)])

            # Get special episode type
            special = mm.get('special',"")
            if special: special = special.strip()

            # Set overrides
            if ovrx:
                if ovrx.has_key('season'):
                    snum = int(ovrx['season'])
                    logthis("Season set by override. Season:",suffix=snum,loglevel=LL.VERBOSE)

                if ovrx.has_key('series_name'):
                    sser = ovrx['series_name']
                    logthis("Series name set by override. Series:",suffix=sser,loglevel=LL.VERBOSE)

            logthis("Matched [%s] with regex:" % (dval),suffix=rgx,loglevel=LL.DEBUG)
            logthis("> Ser[%s] Se#[%s] Ep#[%s] Special[%s]" % (sser,snum,epnum,special),loglevel=LL.DEBUG)

            # Build output fparse array
            fparse = { 'series': sser, 'season': int(snum), 'episode': int(epnum), 'special': special }

            # Add series to tdex
            tdex_id = mdb.series_add(sser,ovrx)

            break

    return (fparse, tdex_id)


def filter_fname(fname):
    """
    Take an input title string that was extracted from a filename, and
    if there are more periods or underscores than spaces, then replace them
    (underscores or periods) with spaces.
    """
    # Count number of spaces, periods, and underscores
    spc = fname.count(' ')
    spd = fname.count('.')
    spu = fname.count('_')

    # No spaces? Something's up
    if spc == 0:
        if spd > spu:
            nout = fname.replace('.',' ')
        else:
            nout = fname.replace('_',' ')
        # fix double-spaces
        nout = nout.replace('  ',' ')
    else:
        # return without changes
        nout = fname

    return fname


def save_checksums(fname,chksums):
    """
    Save checksums to xattribs
    """
    ox = {
            'checksum.md5':   chksums.get('md5',''),
            'checksum.ed2k':  chksums.get('ed2k',''),
            'checksum.crc32': chksums.get('crc32','')
         }
    logthis("Setting checksum xattribs:",suffix=ox,loglevel=LL.DEBUG)
    fsutil.xattr_set(fname, ox)


xaov_map =  {
                'media.seriesname': "series_name",
                'media.season':     "season",
                'media.episode':    "episode",
                'media.xref.tvdb':  "tvdb_id",
                'media.xref.mal':   "mal_id",
                'checksum.md5':     "md5",
                'checksum.ed2k':    "ed2k",
                'checksum.crc32':   "crc32",
                'checksum.sha1':    "sha1",
                'xbake.ignore':     "ignore"
            }

def parse_xattr_overrides(xpath):
    """
    Parse overrides from extended file attributes
    """
    xrides = {}
    xatr = fsutil.xattr_get(xpath)

    for xk,xv in xatr.iteritems():
        if xaov_map.has_key(xk):
            logthis("Got override from xattrib [user.%s]: %s ->" % (xk,xaov_map[xk]),suffix=xv,loglevel=LL.VERBOSE)
            xrides[xaov_map[xk]] = xv

    return xrides


def parse_overrides(xpath):
    """
    Parse overrides file (./.xbake)
    This is a JSON file with special settings for a particular directory.
    Settings include: File ignore list, Series name, tvdb series ID,
    and season number
    """
    xfile = os.path.realpath(xpath + "/" + '.xbake')

    if os.path.exists(xfile):
        logthis("Overrides persent for this directory. Parsing file:",suffix=xfile,loglevel=LL.VERBOSE)
        xrff = open(xfile)
        try:
            xrides = json.loads(xrff.read())
            logthis("Parsed overrides successfully.",loglevel=LL.DEBUG)
        except JSONDecodeError as e:
            logthis("Failed to parse JSON from overrides file:",suffix=xfile,loglevel=LL.ERROR)
            logthis("Parse error:",suffix=e,loglevel=LL.ERROR)
            xrides = {}
        except e:
            logthis("Failed to parse JSON from overrides file:",suffix=xfile,loglevel=LL.ERROR)
            logthis("Other error:",suffix=e,loglevel=LL.ERROR)
            xrides = {}
    else:
        logthis("No overrides for this directory. File does not exist:",suffix=xfile,loglevel=LL.DEBUG)
        xrides = {}
    return xrides


def check_overrides(ovx,cfile):
    """
    Check override ignore list for matches.
    Return: True if match (file should be skipped/ignored)
            False if no match (file should be processed as usual)
    """
    if ovx:
        if ovx.has_key('ignore') and isinstance(ovx['ignore'],list):
            for ii in ovx['ignore']:
                if unicode(ii) == unicode(cfile):
                    return True
    return False

