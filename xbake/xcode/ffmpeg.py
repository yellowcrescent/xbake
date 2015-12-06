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
import shutil

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith

class bpath:
    ffpath = None
    mepath = None
    impath = None
    wppath = None

def locate(prog,isFatal=True):
    """
    Locate path to a binary
    """
    wiout = subprocess.check_output(['whereis',prog])
    bgrp = re.match('^[^:]+: (.+)$', wiout)
    if bgrp:
        gstr = bgrp.groups()[0]
        loclist = gstr.split(' ')
        tpath = loclist[0]
        logthis("Located %s binary:" % prog,suffix=tpath,loglevel=LL.VERBOSE)
        return tpath
    else:
        if isFatal:
            logthis("Unable to locate required binary:",suffix=prog,loglevel=LL.ERROR)
            failwith(ER.DEPMISSING, "External dependency missing. Unable to continue. Aborting")
        return False

def locateAll():
    """
    Locate required binaries (ffmpeg, mkvextract, etc.)
    """
    bpath.ffpath = locate('ffmpeg')
    # check if ffmpeg path auto-detection is set to auto (ffmpeg.path = False)
    # if so, set the path in the ffmpeg option block
    if __main__.xsetup.config['ffmpeg']['path'] == False:
        __main__.xsetup.config['ffmpeg']['path'] = bpath.ffpath

    bpath.mepath = locate('mkvextract')
    bpath.impath = locate('convert')
    bpath.wppath = locate('cwebp')

def version():
    """
    Determine ffmpeg version and build information
    """
    verdata = subprocess.check_output([bpath.ffpath,'-version'])
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

def run(optlist,supout=False):
    """
    Run ffmpeg; Input a list of options; if `supout` is True, then suppress stderr
    """
    logthis("Running ffmpeg with options:",suffix=optlist,loglevel=LL.DEBUG)
    try:
        if supout:
            fout = subprocess.check_output([ bpath.ffpath ] + optlist,stderr=subprocess.STDOUT)
        else:
            fout = subprocess.check_output([ bpath.ffpath ] + optlist)
    except subprocess.CalledProcessError as e:
        logthis("ffmpeg failed:",suffix=e,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL,"Transcoding failed. Unable to continue. Aborting")

    logthis("ffmpeg completed successfully",loglevel=LL.DEBUG)

    return fout

def dumpFonts(vfile,moveto=None):
    """
    Use ffmpeg -dump_attachment to dump font files for baking subs
    """

    prelist = os.listdir(".")
    try:
        subprocess.check_output([bpath.ffpath,'-y','-dump_attachment:t','','-i',vfile],stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logthis("FFmpeg returned non-zero, but dump_attachment is buggy, so it's OK.",loglevel=LL.VERBOSE)

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
        moveto = os.path.expanduser(moveto).rstrip('/')
        curpath = os.path.realpath('.')
        for i in fontlist:
            shutil.move(os.path.realpath(i),os.path.realpath(moveto + '/' + i))
        logthis("Moved fonts to new location:",suffix=os.path.realpath(moveto),loglevel=LL.VERBOSE)

    return fontlist


def dumpSub(vfile,trackid,outfile):
    """
    Use mkvextract to dump subtitle track
    """

    try:
        subprocess.check_output([bpath.mepath,'tracks',vfile,"%d:%s" % (trackid,outfile)])
    except subprocess.CalledProcessError as e:
        logthis("mkvextract failed:",suffix=e,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL,"Sub extraction failed. Unable to continue. Aborting")

    # check for output file
    if not os.path.exists(outfile):
        logthis("Expected output sub file, but not found:",suffix=outfile,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL,"Sub extraction failed. Unable to continue. Aborting")

    logthis("Extracted subtitle file successfully:",suffix=outfile,loglevel=LL.VERBOSE)

def vscap(vfile,offset,outfile):
    """
    Capture frame at specified offset
    """
    try:
        subprocess.check_output([bpath.ffpath,'-y','-ss',offset,'-i',vfile,'-t','1','-r','1',outfile],stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logthis("FFmpeg returned non-zero. Frame capture failed.",loglevel=LL.WARNING)

def im_scale(ifile,ofile,h):
    """
    ImageMagick: Scale image
    """
    try:
        subprocess.check_output([bpath.impath,ifile,'-resize','x%s' % h,ofile],stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logthis("ImageMagick convert failed:",suffix=e,loglevel=LL.ERROR)

def webp_convert(ifile,ofile,m=6,q=90):
    """
    WebP: Convert to WebP format
    """
    try:
        subprocess.check_output([bpath.wppath,'-m',str(m),'-q',str(q),ifile,'-o',ofile],stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logthis("CWebP failed:",suffix=e,loglevel=LL.ERROR)