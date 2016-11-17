#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.mscan.util
Scanner utility functions

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2016 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import sys
import os
import re
import json
import signal
import time
import subprocess
import pwd
import grp
import hashlib

from pymediainfo import MediaInfo

from xbake.common.logthis import *
from xbake.common import fsutil
from xbake.xcode.ffmpeg import bpath  # FIXME


def md5sum(fname):
    return rhash(fname, "md5")['md5']

def checksum(fname):
    return rhash(fname, ["md5", "CRC32", "ed2k"])

def rhash(infile, hlist):
    global rhpath
    if isinstance(hlist, str):
        hxlist = [hlist]
    else:
        hxlist = hlist
    hxpf = ""
    for i in hxlist:
        hxpf += "%%{%s} " % i
    rout = subprocess.check_output([bpath.rhash, '--printf', hxpf, infile])
    rolist = rout.split(' ')
    hout = {}
    k = 0
    for i in rolist:
        try:
            hout[hxlist[k].lower()] = i
        except IndexError:
            break
        k += 1
    return hout

def dstat(infile):
    """
    Wrapper around os.stat(), which returns the output as a dict instead of an object
    """
    fsx = os.stat(infile)
    sout = {
                'dev': fsx.st_dev,
                'ino': fsx.st_ino,
                'mode': fsx.st_mode,
                'nlink': fsx.st_nlink,
                'uid': fsx.st_uid,
                'gid': fsx.st_gid,
                'rdev': fsx.st_rdev,
                'size': fsx.st_size,
                'atime': fsx.st_atime,
                'mtime': fsx.st_mtime,
                'ctime': fsx.st_ctime,
                'blksize': fsx.st_blksize,
                'blocks': fsx.st_blocks
            }
    return sout

def getuser(xuid):
    return pwd.getpwuid(xuid).pw_name

def getgroup(xgid):
    return grp.getgrgid(xgid).gr_name

def getmkey(istat):
    return hashlib.md5(str(istat['ino']) + str(istat['mtime']) + str(istat['size'])).hexdigest()

## Mediainfo parser

class MIP:
    COPY = 1
    INT = 2
    FLOAT = 4
    BOOL = 8
    DATE = 16
    STRCOPY = 32
    LOWER = 256
    DIV1000 = 512

MILUT = {
            'id': MIP.COPY,
            'unique_id': MIP.STRCOPY,
            'format': MIP.COPY |MIP.LOWER,
            'format_profile': MIP.COPY,
            'codec_id': MIP.COPY,
            'duration': MIP.FLOAT |MIP.DIV1000,
            'overall_bit_rate': MIP.FLOAT |MIP.DIV1000,
            'encoded_date': MIP.DATE,
            'writing_application': MIP.COPY,
            'writing_library': MIP.COPY,
            'encoding_settings': MIP.COPY,
            'width': MIP.COPY,
            'height': MIP.COPY,
            'display_aspect_ratio': MIP.COPY,
            'original_display_aspect_ratio': MIP.COPY,
            'frame_rate': MIP.FLOAT,
            'color_space': MIP.COPY,
            'chroma_subsampling': MIP.COPY,
            'bit_depth': MIP.COPY,
            'scan_type': MIP.COPY |MIP.LOWER,
            'title': MIP.COPY,
            'language': MIP.COPY |MIP.LOWER,
            'channel_s': {'do': MIP.COPY, 'name': "channels"},
            'sampling_rate': MIP.COPY,
            'default': MIP.BOOL,
            'forced': MIP.BOOL
         }

def mediainfo(fname):
    global MILUT

    logthis("Parsing mediainfo from file:", suffix=fname, loglevel=LL.VERBOSE)

    # parse output of mediainfo and convert raw XML with pymediainfo
    miobj = MediaInfo.parse(fname)
    miraw = miobj.to_data()['tracks']

    # create outdata for the important stuff
    outdata = {'general': {}, 'video': [], 'audio': [], 'text': [], 'menu': []}

    # interate over data and build nicely pruned output array
    for tt in miraw:
        ttype = tt['track_type'].lower()
        tblock = {}
        for tkey, tval in tt.items():
            # Check all menu items (chapters)
            if ttype == 'menu':
                # We only care about the actual chapters/markers with timestamps
                tss = re.match('^(?P<hour>[0-9]{2})_(?P<min>[0-9]{2})_(?P<msec>[0-9]{5})$', tkey)
                if tss:
                    mts = tss.groupdict()
                    mtt = re.match('^(?P<lang>[a-z]{2})?:?(?P<title>.+)$', tval).groupdict()
                    mti = {
                            'offset': (float(mts['hour']) * 3600.0) + (float(mts['min']) * 60.0) + (float(mts['msec']) / 1000.0),
                            'title': mtt.get('title', ""),
                            'lang': mtt.get('lang', "en"),
                            'tstamp': "%02d:%02d:%06.3f" % (int(mts['hour']), int(mts['min']), (float(mts['msec']) / 1000.0))
                          }
                    outdata['menu'].append(mti)

            # Make sure it's a key we care about
            elif MILUT.has_key(tkey):
                tname = tkey

                # If the object in the LUT is a dict, it has extended info
                if type(MILUT[tkey]) is dict:
                    tcmd = MILUT[tkey]['do']
                    if MILUT[tkey].has_key('opt'):
                        topt = MILUT[tkey]['opt']
                    else:
                        topt = None
                    if MILUT[tkey].has_key('name'):
                        tname = MILUT[tkey]['name']
                else:
                    tcmd = MILUT[tkey]
                    topt = None

                # check for dupes
                if tblock.has_key(tname):
                    logthis("Ignoring duplicate attribute:", suffix=tname, loglevel=LL.VERBOSE)
                    continue

                # exec opcode
                try:
                    if tcmd & MIP.COPY:
                        tblock[tname] = tval
                    elif tcmd & MIP.STRCOPY:
                        tblock[tname] = str(tval)
                    elif tcmd & MIP.INT:
                        tblock[tname] = int(tval)
                    elif tcmd & MIP.FLOAT:
                        tblock[tname] = float(tval)
                    elif tcmd & MIP.BOOL:
                        tblock[tname] = bool(tval)
                    elif tcmd & MIP.DATE:
                        tblock[tname] = int(time.mktime(time.strptime(tval, '%Z %Y-%m-%d %H:%M:%S')))
                    else:
                        failwith(ER.NOTIMPL, "Specified tcmd opcode not implemented.")
                except Exception as e:
                    logthis("Failed to parse mediainfo output:", prefix=tname, suffix=e, loglevel=LL.WARNING)
                    continue

                # post-filters
                if tcmd & MIP.LOWER:
                    tblock[tname] = tblock[tname].lower()
                if tcmd & MIP.DIV1000:
                    tblock[tname] = tblock[tname] / 1000.0

        # add track block to output data
        if ttype == 'general':
            outdata['general'] = tblock
        elif ttype != 'menu':
            outdata[ttype].append(tblock)

    logthis("Got mediainfo for file:\n", suffix=outdata, loglevel=LL.DEBUG2)

    return outdata
