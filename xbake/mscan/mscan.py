#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# mscan - xbake/mscan/mscan.py
# XBake: Media scanner
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

from xbake.mscan import mdb
from xbake.mscan.mdb import MCMP

class DSTS:
    NEW = 'new'
    UNCHANGED = 'unchanged'
    RENAMED = 'renamed'

# File extension filter
fext = re.compile('\.(avi|mkv|mpg|mpeg|wmv|vp8|ogm|mp4|mpv)',re.I)

def run(infile,dreflinks=True,**kwargs):
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

    if conf['run']['single']:
        scan_single(infile)
    else:
        enumdir(infile,dreflinks,conf['scan']['mforce'],conf['scan']['nochecksum'])

    # Connect to Mongo
    #monjer = db.mongo(conf['mongo'])

    logthis("*** Scanning task completed successfully.",loglevel=LL.INFO)


def enumdir(dpath,dreflinks=True,mforce=False,nochecksum=False):

    ddex = {}
    new_files = 0

    for tdir,dlist,flist in os.walk(unicode(dpath),followlinks=dreflinks):
        # get base & parent dir names
        tdir_base = os.path.split(tdir)[1]
        tdir_parent = os.path.split(os.path.split(tdir)[0])[1]

        # Parse overrides for this directory
        ovrx = parse_overrides(tdir)

        logthis("*** Scanning files in directory:",suffix=tdir,loglevel=LL.INFO)

        # enum files in this directory
        for xv in flist:
            xvreal = os.path.realpath(unicode(tdir + '/' + xv))
            xvbase,xvext = os.path.splitext(xv)
            dasc = {}

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

            logthis("Examining file:",suffix=xv,loglevel=LL.INFO)

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
                    # On to the next one...
                    continue

            # Caclulate checksums
            if not nochecksum:
                logthis("Calculating checksum...",loglevel=LL.INFO)
                dasc['checksum'] = util.checksum(xvreal)

            # Get mediainfo
            dasc['mediainfo'] = util.mediainfo(xvreal)

            # Determine series information from path and filename
            dasc['fparse'] = parse_episode_filename(dasc,ovrx)

            # Add filedata to ddex, new_files++, and move on to the next one
            ddex[xv] = dasc
            new_files += 1

    # Enumeration complete
    print("\nOutput:\n%s\n" % (json.dumps(ddex,sort_keys=True,indent=4,separators=(',', ': '))))


def parse_episode_filename(dasc,ovrx):
    # TODO
    fparse = { 'series': None, 'season': None, 'episode': None, 'special': None }
    return fparse


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
            xrides = False
        except e:
            logthis("Failed to parse JSON from overrides file:",suffix=xfile,loglevel=LL.ERROR)
            logthis("Other error:",suffix=e,loglevel=LL.ERROR)
            xrides = False
    else:
        logthis("No overrides for this directory. File does not exist:",suffix=xfile,loglevel=LL.DEBUG)
        xrides = False
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

