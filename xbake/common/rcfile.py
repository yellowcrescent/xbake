#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.common.rcfile
Configuration parser

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2016 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import os
import re
import json
import codecs
import ConfigParser

from xbake import defaults
from xbake.common.logthis import *

rcfiles = ['./xbake.conf', '~/.xbake/xbake.conf', '~/.xbake', '/etc/xbake.conf']
rcpar = None


class XConfig(object):
    """
    Config management object; allow access via attributes or items
    """
    __data = {}

    def __init__(self, idata):
        self.__data = idata

    def _dump(self):
        return json.dumps(self.__data)

    def _todict(self):
        return json.loads(json.dumps(self.__data))

    def _clone(self):
        return XConfig(json.loads(json.dumps(self.__data)))

    def __getattr__(self, aname):
        if aname in self.__data:
            if isinstance(self.__data[aname], dict):
                return XConfig(self.__data[aname])
            else:
                return self.__data[aname]
        elif isinstance(aname, int):
            return self.__data.keys()[aname]
        else:
            raise KeyError(aname)

    def __getitem__(self, aname):
        return self.__getattr__(aname)

    def __setitem__(self, aname, aval):
        self.__data[aname] = aval

    def __str__(self):
        return print_r(self.__data)

    def __repr__(self):
        return "<XConfig>"


def rcList(xtraConf=None):
    """
    build list of config files to parse
    """
    global rcfiles
    rcc = []

    if xtraConf:
        xcf = os.path.expanduser(xtraConf)
        if os.path.exists(xcf):
            rcc.append(xcf)
            logthis("Added rcfile candidate (from command line):", suffix=xcf, loglevel=LL.DEBUG)
        else:
            logthis("Specified rcfile does not exist:", suffix=xcf, loglevel=LL.ERROR)

    for tf in rcfiles:
        ttf = os.path.expanduser(tf)
        logthis("Checking for rcfile candidate", suffix=ttf, loglevel=LL.DEBUG2)
        if os.path.exists(ttf):
            rcc.append(ttf)
            logthis("Got rcfile candidate", suffix=ttf, loglevel=LL.DEBUG2)

    return rcc


def parse(xtraConf=None):
    """
    Parse rcfile (xbake.conf)
    Output: (rcfile, rcdata)
    """
    global rcpar
    # get rcfile list
    rcl = rcList(xtraConf)
    logthis("Parsing any local, user, or system RC files...", loglevel=LL.DEBUG)

    # use ConfigParser to parse the rcfiles
    # only first file is parsed for now, implement override system eventually
    rcpar = ConfigParser.SafeConfigParser()
    rcfile = None
    if len(rcl):
        rcfile = os.path.realpath(rcl[0])
        logthis("Parsing config file:", suffix=rcfile, loglevel=LL.VERBOSE)
        try:
            # use ConfigParser.readfp() so that we can correctly parse UTF-8 stuffs
            # ...damn you python 2 and your shitty unicode bodgery
            with codecs.open(rcfile, 'r', encoding='utf-8') as f:
                rcpar.readfp(f)
        except ConfigParser.ParsingError as e:
            logthis("Error parsing config file: %s" % e, loglevel=LL.ERROR)
            return False

    # build a dict
    rcdict = {}
    rsecs = rcpar.sections()
    logthis("Config sections:", suffix=rsecs, loglevel=LL.DEBUG2)
    for ss in rsecs:
        isecs = rcpar.items(ss)
        rcdict[ss] = {}
        for ii in isecs:
            logthis(">> %s" % ii[0], suffix=ii[1], loglevel=LL.DEBUG2)
            rcdict[ss][ii[0]] = ii[1]

    # return loaded filename and rcdata
    return (rcfile, rcdict)


def merge(inrc, cops):
    """
    Merge options from loaded rcfile with defaults; strip quotes and perform type-conversion.
    Any defined value set in the config will override the default value.
    """
    outrc = {}
    # set defaults first
    for dsec in defaults:
        # create sub dict for this section, if not exist
        if not outrc.has_key(dsec):
            outrc[dsec] = {}
        # loop through the keys
        for dkey in defaults[dsec]:
            logthis("** Option:", prefix="defaults", suffix="%s => %s => '%s'" % (dsec, dkey, defaults[dsec][dkey]), loglevel=LL.DEBUG2)
            outrc[dsec][dkey] = defaults[dsec][dkey]

    # set options defined in rcfile, overriding defaults
    for dsec in inrc:
        # create sub dict for this section, if not exist
        if not outrc.has_key(dsec):
            outrc[dsec] = {}
        # loop through the keys
        for dkey in inrc[dsec]:
            # check if key exists in defaults
            try:
                type(outrc[dsec][dkey])
                keyok = True
            except KeyError:
                keyok = False

            # Strip quotes and perform type-conversion for ints and floats
            # only perform conversion if key exists in defaults
            if keyok:
                if isinstance(outrc[dsec][dkey], bool):
                    try:
                        if qstrip(inrc[dsec][dkey]).lower() in ['y', 'yes', 'on', 't', 'true', '1']:
                            tkval = True
                        elif qstrip(inrc[dsec][dkey]).lower() in ['n', 'no', 'off', 'f', 'false', '0']:
                            tkval = False
                        else:
                            logthis("Unable to cast string to bool:", prefix="%s:%s" % (dsec, dkey), suffix=qstrip(inrc[dsec][dkey]), loglevel=LL.WARNING)
                    except ValueError as e:
                        logexc(e, "Unable to cast string to bool; Value: '%s'" % (qstrip(inrc[dsec][dkey])), prefix="%s:%s" % (dsec, dkey))
                        continue
                elif isinstance(outrc[dsec][dkey], int):
                    try:
                        tkval = int(qstrip(inrc[dsec][dkey]))
                    except ValueError as e:
                        logexc(e, "Unable to convert value to integer. Check config option value. Value: '%s'" % (qstrip(inrc[dsec][dkey])), prefix="%s:%s" % (dsec, dkey))
                        continue
                elif isinstance(outrc[dsec][dkey], float):
                    try:
                        tkval = float(qstrip(inrc[dsec][dkey]))
                    except ValueError as e:
                        logexc(e, "Unable to convert value to integer. Check config option value. Value: '%s'" % (qstrip(inrc[dsec][dkey])), prefix="%s:%s" % (dsec, dkey))
                        continue
                else:
                    tkval = qstrip(inrc[dsec][dkey])
            else:
                tkval = qstrip(inrc[dsec][dkey])

            logthis("** Option set:", prefix="rcfile", suffix="%s => %s => '%s'" % (dsec, dkey, tkval), loglevel=LL.DEBUG2)
            outrc[dsec][dkey] = tkval

    # add in cli options
    for dsec in cops:
        # create sub dict for this section, if not exist
        if not outrc.has_key(dsec):
            outrc[dsec] = {}
        # loop through the keys
        for dkey in cops[dsec]:
            # only if the value has actually been set (eg. non-false)
            if cops[dsec][dkey]:
                logthis("** Option:", prefix="cliopts", suffix="%s => %s => '%s'" % (dsec, dkey, cops[dsec][dkey]), loglevel=LL.DEBUG2)
                outrc[dsec][dkey] = cops[dsec][dkey]

    return outrc


def qstrip(inval):
    """
    Strip quotes from quote-delimited strings
    """
    rxm = re.match('^([\"\'])(.+)(\\1)$', inval)
    if rxm:
        return rxm.groups()[1]
    else:
        return inval

def optexpand(iop):
    """
    expand CLI options like "xcode.scale" from 1D to 2D array/dict (like [xcode][scale])
    """
    outrc = {}
    for i in iop:
        dsec, dkey = i.split(".")
        if not outrc.has_key(dsec):
            outrc[dsec] = {}
        outrc[dsec][dkey] = iop[i]
    logthis("Expanded cli optdex:", suffix=outrc, loglevel=LL.DEBUG2)
    return outrc

def loadConfig(xtraConf=None, cliopts=None):
    """
    Top-level class for loading configuration from xbake.conf
    """
    rcfile, rci = parse(xtraConf)  #pylint: disable=unused-variable
    cxopt = optexpand(cliopts)
    optrc = merge(rci, cxopt)
    return XConfig(optrc)
