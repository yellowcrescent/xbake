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

# Logging
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis

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

