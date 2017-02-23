#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.xcode.ssonly
Screenshot capture

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import os
import re

from xbake.common.logthis import *
from xbake.mscan import util
from xbake.common import db
from xbake.xcode.xcode import sscapture

# Mongo object
monjer = None
config = None


def run(xconfig):
    """
    Implements --ssonly mode
    """
    global monjer, config
    config = xconfig

    # Check input filename
    if not config.run['infile']:
        failwith(ER.OPT_MISSING, "option infile required (-i/--infile)")
    else:
        if not os.path.exists(config.run['infile']):
            failwith(ER.OPT_BAD, "infile [%s] does not exist" % config.run['infile'])
        elif not os.path.isfile(config.run['infile']):
            failwith(ER.OPT_BAD, "infile [%s] is not a regular file" % config.run['infile'])

    # Get video ID (MD5 sum by default)
    if config.run['id']:
        vinfo_id = config.run['id']
    elif config.vid['autoid']:
        vinfo_id = util.md5sum(config.run['infile'])
        logthis("MD5 Checksum:", suffix=vinfo_id, loglevel=LL.INFO)
    else:
        vinfo_id = None

    # Connect to Mongo
    monjer = db.mongo(config.mongo)

    # Grab the frame
    vc_offset = None
    if config.run['vscap']:
        try:
            vc_offset = str(int(config.run['vscap']))
        except ValueError:
            logthis("Invalid vscap offset specified, discarding", loglevel=LL.WARNING)

    if vc_offset is None:
        logthis("No valid frame capture offset specified. Determining one automagically.", loglevel=LL.INFO)
        vc_offset = get_magic_offset(vinfo_id)

    vsdata = sscapture(config, vc_offset, vinfo_id)
    tstatus('output', event='vscap', output=vsdata)

    if vsdata is not None:
        if not config.run['noupdate']:
            # Update Mongo entry
            zdata = monjer.findOne('videos', {'_id': vinfo_id})
            if zdata:
                zdata['vscap'] = vsdata
                monjer.upsert('videos', vinfo_id, zdata)
                logthis("Entry updated OK", loglevel=LL.INFO)
            else:
                logthis("No entry found, skipping update")

        logthis("*** Screenshot task completed successfully.", loglevel=LL.INFO)
        #tstatus('complete', status='ok')
        retval = 0
    else:
        logthis("!! Screenshot task failed.", loglevel=LL.ERROR)
        #tstatus('complete', status='fail')
        retval = 1
    return retval


def get_magic_offset(vid=None):
    """
    if no vscap offset was set, let's choose something somewhat sensible
    """
    global monjer

    base_offset = None
    if vid is not None:
        # get chapter list
        try:
            vdata = monjer.findOne("files", {'_id': vid})
            clist = vdata['mediainfo']['menu']
        except Exception as e:
            logthis("Failed to retrieve menu list for input file:", suffix=e, loglevel=LL.VERBOSE)
            clist = []

        # filter out any nasties
        cfilter = re.compile('(^(nc)?(op|ed)$|intro|outro|endcard|title|synopsis|preview|recap|last|eyecatch|interlude|break)', re.I)
        clist = filter(lambda x: not cfilter.search(x['title']), clist)

        if len(clist) > 0:
            # sort by offset
            clist = sorted(clist, key=lambda x: x['offset'])
            cpick = int(len(clist) / 1.5)
            base_offset = clist[cpick]['offset']
        else:
            try:
                # choose a frame about 1/3 through the video
                base_offset = int(vdata['mediainfo']['general']['duration'] * 0.30)
            except:
                base_offset = None

    if base_offset is None:
        # 140, yolo
        base_offset = 140.0

    # add 8 seconds to catch start of the scene,
    # hopefully missing any titles or fade-in
    return int(base_offset + 8.0)
