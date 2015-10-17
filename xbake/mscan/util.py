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

def rhash(infile,hlist):
    global rhpath
    if type(hlist) == str:
        hxlist = [ hlist ]
    hxpf = ""
    for i in hxlist:
        hxpf += "%%{%s} " % i
    rout = subprocess.check_output([rhpath,'--printf',hxpf,infile])
    rolist = rout.split(' ')
    hout = {}
    k = 0
    for i in rolist:
        try:
            hout[hxlist[k]] = i
        except IndexError:
            break
        k += 1
    return hout

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
            # Make sure it's a key we care about
            if milut.has_key(tkey):
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