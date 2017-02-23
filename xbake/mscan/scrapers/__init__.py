#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.mscan.scrapers
Scraper functions

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import os
import sys
import re

from xbake.common.logthis import *

modlist = {}

def loadModules(moddir=None):
    """load modules from 'modules' subdir, or specified path, moddir"""
    global modlist

    if moddir:
        modbase = moddir
    else:
        modbase = os.path.dirname(os.path.realpath(__file__))
    logthis("Loading modules from", suffix=modbase, loglevel=LL.VERBOSE)
    dlist = os.listdir(modbase)

    packlist = []
    for tf in dlist:
        if tf == '__init__.py':
            logthis("skipping __init__.py", loglevel=LL.DEBUG)
            continue
        logthis("checking file/dir:", suffix=tf, loglevel=LL.DEBUG)
        trp = os.path.realpath(modbase + '/' + tf)
        if os.path.isdir(trp) and os.path.exists(trp + '/__init__.py'):
            logthis("++ added directory:", suffix=tf, ccode=C.GRN, loglevel=LL.DEBUG)
            packlist.append(trp)
        elif re.match(r'.*\.py$', trp):
            logthis("++ added file:", suffix=tf, ccode=C.GRN, loglevel=LL.DEBUG)
            packlist.append(trp)

    packout = {}
    for tp in packlist:
        # determine module name from file or dir
        if os.path.isdir(tp):
            packname = os.path.basename(tp)
        else:
            packname = os.path.basename(tp).replace('.py', '')

        # load the module
        logthis(">> Loading module", suffix=packname, loglevel=LL.VERBOSE)
        try:
            packout[packname] = __import__("xbake.mscan.scrapers." + packname, fromlist=['*'])
        except Exception as e:
            logexc(e, "Failed to load module", prefix=packname)
            continue

    modlist = packout
    return packout


def getModuleList():
    """return list of modules and module info"""
    global modlist

    packinfo = []
    for tm in modlist:
        packinfo.append({'name': tm, 'desc': modlist[tm].__desc__, 'author': modlist[tm].__author__,
                         'version': modlist[tm].__version__, 'date': modlist[tm].__date__})

    return packinfo


def scrape(modname, tdex_id, tdex_data, xconfig):
    """
    Run the specified scraper module (@modname);
    pass in an @tdex_id, @tdex_data, and main XConfig object (@xconfig)
    """
    global modlist

    if modlist.has_key(modname):
        if modlist[modname].__dict__.has_key('run'):
            if callable(modlist[modname].run):
                logthis(">> Executing module entry point function", suffix=modname+'.run()', loglevel=LL.DEBUG)
                return modlist[modname].run(tdex_id, tdex_data, xconfig)
            else:
                failwith(ER.MODERROR, "Module contains a conflicting non-callable 'run' object")
        else:
            failwith(ER.MODERROR, "Module is missing run() entry point function")
    else:
        failwith(ER.MODNOTFOUND, "No module named %s found" % (modname))
