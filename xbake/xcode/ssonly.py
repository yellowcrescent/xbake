#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# ssonly - xbake/xcode/ssonly.py
# XBake: Screenshot Capture
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_xbake
#
# Copyright (c) 2015-2016 J. Hipps / Neo-Retro Group
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

from xbake.common.logthis import *
from xbake.xcode import ffmpeg
from xbake.mscan import util
from xbake.common import db
from xbake.xcode.xcode import sscapture

# Mongo object
monjer = None

def run(infile,id=None,**kwargs):
    """
    Implements --ssonly mode
    """
    global monjer
    conf = __main__.xsetup.config

    # Check input filename
    if not infile:
        failwith(ER.OPT_MISSING, "option infile required (-i/--infile)")
    else:
        if not os.path.exists(infile):
            failwith(ER.OPT_BAD, "infile [%s] does not exist" % infile)
        elif not os.path.isfile(infile):
            failwith(ER.OPT_BAD, "infile [%s] is not a regular file" % infile)

    # Get video ID (MD5 sum by default)
    if conf['run']['id']:
        vinfo_id = conf['run']['id']
    elif conf['vid']['autoid']:
        vinfo_id = util.md5sum(infile)
        logthis("MD5 Checksum:",suffix=vinfo.id,loglevel=LL.INFO)
    else:
        vinfo_id = None

    # Connect to Mongo
    monjer = db.mongo(conf['mongo'])

    # Grab the frame
    if conf['run']['vscap']:
        vc_offset = conf['run']['vscap']
    else:
        vc_offset = get_magic_offset(vinfo_id)
        logthis("No frame capture offset specified. Determining one automagically.", loglevel=LL.INFO)

    vsdata = sscapture(infile,conf['run']['vscap'])

    # Update Mongo entry
    zdata = monjer.findOne('videos', { '_id': vinfo_id })
    if zdata:
        zdata['vscap'] = vsdata
        monjer.upsert('videos', vinfo_id, zdata)
        logthis("Entry updated OK",loglevel=LL.INFO)
    else:
        logthis("No entry found, skipping update")

    logthis("*** Screenshot task completed successfully.",loglevel=LL.INFO)
    return 0


def get_magic_offset(id):
    """
    if no vscap offset was set, let's choose something somewhat sensical
    """
    if vinfo_id:
        # get chapter list
        try:
            vdata = monjer.findOne("files", { '_id': id })
            clist = vdata['mediainfo']['menu']
        except Exception as e:
            logthis("Failed to retrieve menu list for input file:",suffix=e,loglevel=LL.VERBOSE)
            clist = []

        # filter out any nasties
        cfilter = re.compile('(^(nc)?(op|ed)$|intro|synopsis|preview|recap|last|eyecatch|interlude|break)',re.I)
        clist = filter(lambda x: not cfilter.search(x['title']), clist)

        if len(clist) > 0:
            # sort by offset
            clist = sorted(clist, key=lambda x: x['offset'])
            cpick = int(len(clist) / 1.5)
            base_offset = clist[cpick]['offset']
        else:
            base_offset = None

    if base_offset is None:
        # 440, yolo
        base_offset = 440.0

    # add 8 seconds to catch start of the scene,
    # hopefully missing any titles or fade-in
    return int(base_offset + 8.0)
