#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# util - xbake/mscan/util.py
# XBake: Scanner Utility Functions
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
import pwd
import grp
import hashlib
from pymediainfo import MediaInfo

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith

rhpath = '/usr/bin/rhash'

def md5sum(fname):
    return rhash(fname, "md5")['md5']

def checksum(fname):
    return rhash(fname, ["md5","CRC32","ed2k"])

def rhash(infile,hlist):
    global rhpath
    if isinstance(hlist,str):
        hxlist = [ hlist ]
    else:
        hxlist = hlist
    hxpf = ""
    for i in hxlist:
        hxpf += "%%{%s} " % i
    rout = subprocess.check_output([rhpath,'--printf',hxpf,infile])
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
    sout =  {
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
    LOWER = 256
    DIV1000 = 512

milut =  {
            'id': MIP.COPY,
            'unique_id': MIP.COPY,
            'format': MIP.COPY|MIP.LOWER,
            'format_profile': MIP.COPY,
            'codec_id': MIP.COPY,
            'duration': MIP.FLOAT|MIP.DIV1000,
            'overall_bit_rate': MIP.COPY,
            'encoded_date': MIP.DATE,
            'writing_application': MIP.COPY,
            'writing_library': MIP.COPY,
            'encoding_settings': MIP.COPY,
            'width': MIP.COPY,
            'height': MIP.COPY,
            'display_aspect_ratio': MIP.COPY,
            'frame_rate': MIP.FLOAT,
            'color_space': MIP.COPY,
            'chroma_subsampling': MIP.COPY,
            'bit_depth': MIP.COPY,
            'scan_type': MIP.COPY|MIP.LOWER,
            'title': MIP.COPY,
            'language': MIP.COPY|MIP.LOWER,
            'channel_s': { 'do': MIP.COPY, 'name': "channels" },
            'sampling_rate': MIP.COPY,
            'default': MIP.BOOL,
            'forced': MIP.BOOL
         }

def mediainfo(fname):
    global milut

    logthis("Parsing mediainfo from file:",suffix=fname,loglevel=LL.VERBOSE)

    # parse file and read convert raw XML with pymediainfo
    miobj = MediaInfo.parse(fname)
    miraw = miobj.to_data()['tracks']

    # create outdata for the important stuff
    outdata = { 'general': {}, 'video': [], 'audio': [], 'text': [], 'menu': [] }

    # interate over data and build nicely pruned output array
    for tt in miraw:
        ttype = tt['track_type'].lower()
        tblock = {}
        for tkey,tval in tt.items():
            # Check all menu items (chapters)
            if ttype == 'menu':
                # We only care about the actual chapters/markers with timestamps
                tss = re.match('^(?P<hour>[0-9]{2})_(?P<min>[0-9]{2})_(?P<msec>[0-9]{5})$',tkey)
                if tss:
                    mts = tss.groupdict()
                    mtt = re.match('^(?P<lang>[a-z]{2}):(?P<title>.+)$',tval).groupdict()
                    mti = {
                            'offset': (float(mts['hour']) * 3600.0) + (float(mts['min']) * 60.0) + (float(mts['msec']) / 1000.0),
                            'title': mtt['title'],
                            'lang': mtt['lang'],
                            'tstamp': "%02d:%02d:%06.3f" % (int(mts['hour']),int(mts['min']),(float(mts['msec']) / 1000.0))
                          }
                    outdata['menu'].append(mti)

            # Make sure it's a key we care about
            elif milut.has_key(tkey):
                tname = tkey

                # If the object in the LUT is a dict, it has extended info
                if type(milut[tkey]) is dict:
                    tcmd = milut[tkey]['do']
                    if milut[tkey].has_key('opt'):
                        topt = milut[tkey]['opt']
                    else:
                        topt = None
                    if milut[tkey].has_key('name'):
                        tname = milut[tkey]['name']
                else:
                    tcmd = milut[tkey]
                    topt = None

                # exec opcode
                if tcmd & MIP.COPY:
                    tblock[tname] = tval
                elif tcmd & MIP.INT:
                    tblock[tname] = int(tval)
                elif tcmd & MIP.FLOAT:
                    tblock[tname] = float(tval)
                elif tcmd & MIP.BOOL:
                    tblock[tname] = bool(tval)
                elif tcmd & MIP.DATE:
                    tblock[tname] = int(time.mktime(time.strptime(tval,'%Z %Y-%m-%d %H:%M:%S')))
                else:
                    failwith(ER.NOTIMPL, "Specified tcmd opcode not implemented")

                # post-filters
                if tcmd & MIP.LOWER:
                    tblock[tname] = tblock[tname].lower()
                if tcmd & MIP.DIV1000:
                    tblock[tname] = tblock[tname] / 1000.0

        # add track block to output data
        if ttype == 'general':
            outdata['general'] = tblock
        else:
            outdata[ttype].append(tblock)

    logthis("Got mediainfo for file:\n",suffix=outdata,loglevel=LL.DEBUG2)

    return outdata