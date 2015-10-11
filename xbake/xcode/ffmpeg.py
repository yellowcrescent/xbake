#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# yc_xbake
# YC XBake: Video file scanning, renaming, sub baking and transcoding utility
#
# @version  0.10
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_xbake
#
# Copyright (c) 2013-2015 J. Hipps / Neo-Retro Group
#
# https://ycnrg.org/
#
# @deps     xbake
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

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith

ffpath = None

def locate(prog='ffmpeg'):
    """
    Locate path to ffmpeg binary
    """
    global ffpath
    wiout = subprocess.check_output(['whereis',prog])
    gstr = re.match('^[^:]+: (.+)$', wiout).groups()[0]
    loclist = gstr.split(' ')
    ffpath = loclist[0]
    logthis("Located ffmpeg binary:",suffix=ffpath,loglevel=LL.VERBOSE)

    # check if ffmpeg path auto-detection is set to auto (ffmpeg.path = False)
    # if so, set the path in the ffmpeg option block
    if __main__.xsetup.config['ffmpeg']['path'] == False:
        __main__.xsetup.config['ffmpeg']['path'] = ffpath

    return ffpath

def version():
    """
    Determine ffmpeg version and build information
    """
    global ffpath
    verdata = subprocess.check_output([ffpath,'-version'])
    vdx = {
            'version': re.match('^ffmpeg version ([^ ]+).*',verdata,re.I|re.S|re.M).groups()[0],
            'date': re.match('.*^built on (.+) with.*$',verdata,re.I|re.S|re.M).groups()[0],
            'config': re.match('.*^configuration: (.+?)$',verdata,re.I|re.M|re.S).groups()[0],
            'libavutil': re.match('.*^libavutil\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ',''),
            'libavcodec': re.match('.*^libavcodec\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ',''),
            'libavformat': re.match('.*^libavformat\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ',''),
            'libavdevice': re.match('.*^libavdevice\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ',''),
            'libavfilter': re.match('.*^libavfilter\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ',''),
            'libswscale': re.match('.*^libswscale\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ',''),
            'libswresample': re.match('.*^libswresample\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ',''),
            'libpostproc': re.match('.*^libpostproc\s*(.+?) \/.*$',verdata,re.I|re.S|re.M).groups()[0].replace(' ','')
        }
    return vdx

def run(optlist):
    """
    Run ffmpeg; Input a list of options
    """
    global ffpath

    logthis("Running ffmpeg with options:",suffix=optlist,loglevel=LL.VERBOSE)
    try:
        fout = subprocess.check_output([ ffpath ] + optlist)
    except subprocess.CalledProcessError as e:
        logthis("ffmpeg failed:",suffix=e,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL,"Transcoding failed. Unable to continue. Aborting")

    logthis("ffmpeg completed successfully",loglevel=LL.INFO)

    return fout

def dumpFonts(vfile,moveto=None):
    """
    Use ffmpeg -dump_attachment to dump font files for baking subs
    """
    global ffpath

    prelist = os.listdir(".")
    try:
        subprocess.check_output([ffpath,'-y','-dump_attachment:t','','-i',vfile])
    except subprocess.CalledProcessError as e:
        logthis("FFmpeg returned non-zero, but dump_attachment is buggy, so it's OK.",loglevel=LL.WARNING)

    # get fonts that were dumped
    postlist = os.listdir(".")
    fontlist = list(set(postlist).difference(prelist))
    if not len(fontlist):
        logthis("Warning: No (new) fonts were dumped",loglevel=LL.WARNING)
    else:
        logthis("New fonts dumped:",suffix=len(fontlist),loglevel=LL.VERBOSE)
        logthis("Fonts:",suffix=fontlist,loglevel=LL.DEBUG)

    # move fonts to another directory, if enabled
    if moveto:
        curpath = os.path.realpath('.')
        for i in fontlist:
            os.rename(os.path.realpath(i),os.path.realpath(moveto + '/' + i))
        logthis("Moved fonts to new location:",suffix=os.path.realpath(moveto),loglevel=LL.VERBOSE)

    return fontlist


def dumpSub(vfile,trackid,outfile):
    """
    Use mkvextract to dump subtitle track
    """
    mepath = '/usr/bin/mkvextract'

    try:
        subprocess.check_output([mepath,'tracks',vfile,"%d:%s" % (trackid,outfile)])
    except subprocess.CalledProcessError as e:
        logthis("mkvextract failed:",suffix=e,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL,"Sub extraction failed. Unable to continue. Aborting")

    # check for output file
    if not os.path.exists(outfile):
        logthis("Expected output sub file, but not found:",suffix=outfile,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL,"Sub extraction failed. Unable to continue. Aborting")

    logthis("Extracted subtitle file successfully:",suffix=outfile,loglevel=LL.VERBOSE)
