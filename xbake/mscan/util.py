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

import os
import re
import time
import subprocess
import pwd
import grp
import hashlib

from pymediainfo import MediaInfo

from xbake.common.logthis import *
from xbake.xcode.ffmpeg import bpath  # FIXME


def md5sum(fname):
    """
    Use rhash to calculate the MD5 checksum of @fname, then return MD5 as a string
    """
    return rhash(fname, "md5")['md5']

def checksum(fname):
    """
    Use rhash to calculate checksums of @fname, then return as a dict {md5, crc32, ed2k}
    """
    return rhash(fname, ["md5", "CRC32", "ed2k"])

def rhash(infile, hlist):
    """
    Execute rhash (external binary) to calculate a list of specified hashes @hlist against @infile
    """
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
    """convert uid to username"""
    return pwd.getpwuid(xuid).pw_name

def getgroup(xgid):
    """convert gid to group name"""
    return grp.getgrgid(xgid).gr_name

def getmkey(istat):
    """calculate mkey as an MD5 of inode number + mtime + size"""
    return hashlib.md5(str(istat['ino']) + str(istat['mtime']) + str(istat['size'])).hexdigest()

def normalize(xname):
    """
    Normalize input string for use as a tdex_id
    """
    nrgx = r'[\'`\-\?!%&\*@\(\)#:,\.\/\\;\+=\[\]\{\}\$\<\>]'
    urgx = r'[ ★☆]'
    return re.sub(urgx, '_', re.sub(nrgx, '', xname)).lower().strip()

def deepcopy(src):
    """
    perform a hacky "deep copy" of a dict by converting to/from JSON
    """
    return json.loads(json.dumps(src))

def mts_parse(tsstr, mbase=1):
    """
    parse MediaInfo-style absolute timestamp (eg. '00:06:11.950000000')
    use @mbase=1000 to rebase the number in millseconds rather than seconds
    """
    tacc = 0.0
    tparts = tsstr.split(':')
    tparts.reverse()
    for tplace, tseg in enumerate(tparts):
        tmul = float(60**tplace)
        tacc += tmul * float(tseg)
    return tacc * float(mbase)


## Mediainfo parser

class MIP:
    """mediainfo parser opcodes"""
    COPY = 1
    INT = 2
    FLOAT = 4
    BOOL = 8
    DATE = 16
    STRCOPY = 32
    LOWER = 256
    DIV1000 = 512
    TSTAMP = 1024
    TSTAMP_FB = 2048

# MILUT: MediaInfo LookUp Table
# map each key to opcodes that transform/coerce the value into something nice
MILUT = {
            'id': MIP.COPY,
            'unique_id': MIP.STRCOPY,
            'format': MIP.COPY|MIP.LOWER,
            'format_profile': MIP.COPY,
            'codec_id': MIP.COPY,
            'duration': MIP.FLOAT|MIP.DIV1000|MIP.TSTAMP_FB,
            'overall_bit_rate': MIP.FLOAT|MIP.DIV1000,
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
            'scan_type': MIP.COPY|MIP.LOWER,
            'title': MIP.COPY,
            'language': MIP.COPY|MIP.LOWER,
            'channel_s': {'do': MIP.COPY, 'name': "channels"},
            'sampling_rate': MIP.COPY,
            'default': MIP.BOOL,
            'forced': MIP.BOOL
         }

def mediainfo(fname):
    """
    Use PyMediainfo to retrieve info about @fname, then parse and filter this
    into a more usable format, which is returned as a dict
    """
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
            elif tkey in MILUT:
                tname = tkey

                # check for dupes
                if tname in tblock:
                    logthis("Ignoring duplicate attribute:", suffix=tname, loglevel=LL.VERBOSE)
                    continue

                # If the object in the LUT is a dict, it has extended info
                if isinstance(MILUT[tkey], dict):
                    tcmd = MILUT[tkey]['do']
                    if 'opt' in MILUT[tkey]:
                        topt = MILUT[tkey]['opt']  # pylint: disable=unused-variable
                    else:
                        topt = None
                    if MILUT[tkey].has_key('name'):
                        tname = MILUT[tkey]['name']
                else:
                    tcmd = MILUT[tkey]
                    topt = None

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
                    if tcmd & MIP.TSTAMP_FB:
                        try:
                            tblock[tname] = mts_parse(tval, mbase=1000)
                        except Exception as e:
                            logthis("Failed to parse mediainfo output (TSTAMP_FB also failed):", prefix=tname, suffix=e, loglevel=LL.WARNING)
                            continue
                    else:
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
