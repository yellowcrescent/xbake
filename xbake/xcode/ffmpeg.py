#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.xcode.ffmpeg
FFmpeg & friends interface

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2016 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import os
import re
import subprocess
import shutil

from xbake.common.logthis import *


class bpath:
    """container class for external tool paths"""
    ffpath = None
    mepath = None
    impath = None
    wppath = None
    rhash = None

def locate(prog, isFatal=True):
    """
    Locate path to a binary
    """
    wiout = subprocess.check_output(['whereis', prog])
    bgrp = re.match('^[^:]+: (.+)$', wiout)
    if bgrp:
        gstr = bgrp.groups()[0]
        loclist = gstr.split(' ')
        tpath = loclist[0]
        logthis("Located %s binary:" % prog, suffix=tpath, loglevel=LL.VERBOSE)
        return tpath
    else:
        if isFatal:
            logthis("Unable to locate required binary:", suffix=prog, loglevel=LL.ERROR)
            failwith(ER.DEPMISSING, "External dependency missing. Unable to continue. Aborting")
        return False

def locateAll(xconfig):
    """
    Locate required binaries (ffmpeg, mkvextract, etc.)
    """
    bpath.ffpath = locate('ffmpeg')
    # check if ffmpeg path auto-detection is set to auto (ffmpeg.path = None)
    # if so, set the path in the ffmpeg option block
    if xconfig.ffmpeg['path'] is None:
        xconfig.ffmpeg['path'] = bpath.ffpath

    bpath.mepath = locate('mkvextract')
    bpath.impath = locate('convert')
    bpath.wppath = locate('cwebp')
    bpath.rhash = locate('rhash')

def version():
    """
    Determine ffmpeg version and build information
    """
    verdata = subprocess.check_output([bpath.ffpath, '-version'])
    vdx = {
            'version': vmatch(r'^ffmpeg version ([^ ]+).*', verdata),
            'date': vmatch(r'.*^built on (.+) with.*$', verdata),
            'config': vmatch(r'.*^configuration: (.+?)$', verdata),
            'libavutil': vmatch(r'.*^libavutil\s*(.+?) \/.*$', verdata),
            'libavcodec': vmatch(r'.*^libavcodec\s*(.+?) \/.*$', verdata),
            'libavformat': vmatch(r'.*^libavformat\s*(.+?) \/.*$', verdata),
            'libavdevice': vmatch(r'.*^libavdevice\s*(.+?) \/.*$', verdata),
            'libavfilter': vmatch(r'.*^libavfilter\s*(.+?) \/.*$', verdata),
            'libswscale': vmatch(r'.*^libswscale\s*(.+?) \/.*$', verdata),
            'libswresample': vmatch(r'.*^libswresample\s*(.+?) \/.*$', verdata),
            'libpostproc': vmatch(r'.*^libpostproc\s*(.+?) \/.*$', verdata)
        }
    return vdx

def vmatch(regex, instr, wstrip=False):
    """
    safely match and extract ffmpeg version infos
    """
    rrx = re.match(regex, instr, re.I |re.S |re.M)
    if rrx:
        if wstrip:
            return rrx.groups()[0].replace(' ', '')
        else:
            return rrx.groups()[0]
    else:
        return None

def run(optlist, supout=False):
    """
    Run ffmpeg; Input a list of options; if @supout is True, then suppress stderr
    """
    logthis("Running ffmpeg with options:", suffix=optlist, loglevel=LL.DEBUG)
    try:
        if supout:
            fout = subprocess.check_output([bpath.ffpath] + optlist, stderr=subprocess.STDOUT)
        else:
            fout = subprocess.check_output([bpath.ffpath] + optlist)
    except subprocess.CalledProcessError as e:
        logthis("ffmpeg failed:", suffix=e, loglevel=LL.ERROR)
        failwith(ER.PROCFAIL, "Transcoding failed. Unable to continue. Aborting")

    logthis("ffmpeg completed successfully", loglevel=LL.DEBUG)

    return fout

def dumpFonts(vfile, moveto=None):
    """
    Use ffmpeg -dump_attachment to dump font files for baking subs
    """

    prelist = os.listdir(".")
    try:
        subprocess.check_output([bpath.ffpath, '-y', '-dump_attachment:t', '', '-i', vfile], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        logthis("FFmpeg returned non-zero, but dump_attachment is buggy, so it's OK.", loglevel=LL.VERBOSE)

    # get fonts that were dumped
    postlist = os.listdir(".")
    fontlist = list(set(postlist).difference(prelist))
    if not len(fontlist):
        logthis("Warning: No (new) fonts were dumped", loglevel=LL.WARNING)
    else:
        logthis("New fonts dumped:", suffix=len(fontlist), loglevel=LL.VERBOSE)
        logthis("Fonts:", suffix=fontlist, loglevel=LL.DEBUG)

    # move fonts to another directory, if enabled
    if moveto:
        moveto = os.path.expanduser(moveto).rstrip('/')
        for i in fontlist:
            shutil.move(os.path.realpath(i), os.path.realpath(moveto + '/' + i))
        logthis("Moved fonts to new location:", suffix=os.path.realpath(moveto), loglevel=LL.VERBOSE)

    return fontlist


def dumpSub(vfile, trackid, outfile):
    """
    Use mkvextract to dump subtitle track @trackid from @vfile to @outfile
    """
    # run mkvextract to dump subtitle track
    try:
        subprocess.check_output([bpath.mepath, 'tracks', vfile, "%d:%s" % (trackid, outfile)])
    except subprocess.CalledProcessError as e:
        logexc(e, "mkvextract failed")
        failwith(ER.PROCFAIL, "Sub extraction failed. Unable to continue. Aborting")

    # check for output file
    if not os.path.exists(outfile):
        logthis("Expected output sub file, but not found:", suffix=outfile, loglevel=LL.ERROR)
        failwith(ER.PROCFAIL, "Sub extraction failed. Unable to continue. Aborting")

    logthis("Extracted subtitle track successfully:", suffix=outfile, loglevel=LL.VERBOSE)

def vscap(vfile, offset, outfile):
    """
    Capture frame at specified offset
    """
    try:
        subprocess.check_output([bpath.ffpath, '-y', '-ss', str(offset), '-i', vfile, '-t', '1', '-r', '1', outfile], stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        logexc(e, "FFmpeg returned non-zero. Frame capture failed")
        return False

def im_scale(ifile, ofile, h):
    """
    ImageMagick: Scale image
    """
    try:
        subprocess.check_output([bpath.impath, ifile, '-resize', 'x%s' % h, ofile], stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        logexc(e, "ImageMagick convert failed")
        return False

def webp_convert(ifile, ofile, m=6, q=90):
    """
    WebP: Convert to WebP format
    """
    try:
        subprocess.check_output([bpath.wppath, '-m', str(m), '-q', str(q), ifile, '-o', ofile], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logexc(e, "cwebp conversion failed")
