#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# rcfile - xbake/common/rcfile.py
# XBake: RCFile functions
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_cpx
#
# Copyright (c) 2015 J. Hipps / Neo-Retro Group
#
# https://ycnrg.org/
#
###############################################################################

import os
import sys
import __main__
import traceback
import inspect
import logging
import logging.handlers
import signal
from ConfigParser import SafeConfigParser

# Logging
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis

# RCfile list
rcfiles = [ './xbake.conf', '~/.xbake/xbake.conf', '~/.xbake', '/etc/xbake.conf' ]

def rcList(xtraConf=None):
    global rcfiles
    rcc = []

    if xtraConf:
        xcf = os.path.expanduser(xtraConf)
        if os.path.exists(xcf):
            rcc.append(xcf)
            logthis("Added rcfile candidate (from command line):",suffix=xcf,loglevel=LL.DEBUG)
        else:
            logthis("Specified rcfile does not exist:",suffix=xcf,loglevel=LL.ERROR)

    for tf in rcfiles:
        ttf = os.path.expanduser(tf)
        logthis("Checking for rcfile candidate",suffix=ttf,loglevel=LL.DEBUG2)
        if os.path.exists(ttf):
            rcc.append(ttf)
            logthis("Got rcfile candidate",suffix=ttf,loglevel=LL.DEBUG)

    return rcc


def parse(xtraConf=None):
    # get rcfile list
    rcl = rcList(xtraConf)
    logthis("Parsing any local, user, or sytem RC files...",loglevel=LL.VERBOSE)

    # use ConfigParser to parse the rcfiles
    rcpar = SafeConfigParser()
    rcpar.read(rcl)

    # build a dict
    rcdict = {}
    rsecs = rcpar.sections()
    logthis("Config sections:",suffix=rsecs,loglevel=LL.DEBUG2)
    for ss in rsecs:
        isecs = rcpar.items(ss)
        rcdict[ss] = {}
        for ii in isecs:
            logthis(">> %s" % ii[0],suffix=ii[1],loglevel=LL.DEBUG2)
            rcdict[ss][ii[0]] = ii[1]
    return rcdict
