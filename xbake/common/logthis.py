#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.common.logthis
Logging & exception handling facilities

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""
# pylint: disable=missing-docstring

import os
import sys
import inspect
import json

class C:
    """ANSI Colors"""
    OFF = '\033[m'
    HI = '\033[1m'
    BLK = '\033[30m'
    RED = '\033[31m'
    GRN = '\033[32m'
    YEL = '\033[33m'
    BLU = '\033[34m'
    MAG = '\033[35m'
    CYN = '\033[36m'
    WHT = '\033[37m'
    B4 = '\033[4D'
    CLRSCR = '\033[2J'
    CLRLINE = '\033[K'
    HOME = '\033[0;0f'
    XCLEAR = '\033[2J\033[K\033[K'

    def nocolor(self):
        self.OFF = ''
        self.HI = ''
        self.BLK = ''
        self.RED = ''
        self.GRN = ''
        self.YEL = ''
        self.BLU = ''
        self.MAG = ''
        self.CYN = ''
        self.WHT = ''
        self.B4 = ''
        self.CLRSCR = ''
        self.CLRLINE = ''
        self.HOME = ''
        self.XCLEAR = ''

class ER:
    # pylint: disable=bad-whitespace
    OPT_MISSING = 1
    OPT_BAD     = 2
    CONF_BAD    = 3
    PROCFAIL    = 4
    NOTFOUND    = 5
    UNSUPPORTED = 6
    DEPMISSING  = 7
    NOTIMPL     = 8
    MODERROR    = 9
    MODNOTFOUND = 10
    lname = {
                0: 'none',
                1: 'opt_missing',
                2: 'opt_bad',
                3: 'conf_bad',
                4: 'procfail',
                5: 'notfound',
                6: 'unsupported',
                7: 'depmissing',
                8: 'notimpl',
                9: 'moderror',
                10: 'modnotfound'
            }

class xbError(Exception):
    """XBake Exception class"""
    # pylint: disable=super-init-not-called
    def __init__(self, etype):
        self.etype = etype
    def __str__(self):
        return ER.lname[self.etype]

class LL:
    # pylint: disable=bad-whitespace
    SILENT   = 0
    CRITICAL = 2
    ERROR    = 3
    WARNING  = 4
    PROMPT   = 5
    INFO     = 6
    VERBOSE  = 7
    DEBUG    = 8
    DEBUG2   = 9
    lname = {
                0: 'silent',
                2: 'critical',
                3: 'error',
                4: 'warning',
                5: 'prompt',
                6: 'info',
                7: 'verbose',
                8: 'debug',
                9: 'debug2'
            }

# set default loglevel
g_loglevel = LL.INFO

_config = None

def logthis(logline, loglevel=LL.DEBUG, prefix=None, suffix=None, ccode=None):
    """
    Global logging function; handles log line composition and prints messages to the console
    and log file
    """
    # pylint: disable=redefined-outer-name
    global g_loglevel

    zline = ''
    if not ccode:
        if loglevel == LL.ERROR: ccode = C.RED
        elif loglevel == LL.WARNING: ccode = C.YEL
        elif loglevel == LL.PROMPT: ccode = C.WHT
        else: ccode = ""
    if prefix: zline += C.WHT + unicode(prefix) + ": " + C.OFF
    zline += ccode + logline + C.OFF
    if suffix: zline += " " + C.CYN + unicode(suffix) + C.OFF

    # get traceback info
    lframe = inspect.stack()[1][0]
    lfunc = inspect.stack()[1][3]
    mod = inspect.getmodule(lframe)
    lline = inspect.getlineno(lframe)
    lfile = inspect.getsourcefile(lframe)
    lfile = os.path.splitext(os.path.basename(lfile))[0]

    if mod:
        lmodname = str(mod.__name__)
    else:
        lmodname = str(__name__)
    if lmodname == "__main__":
        lmodname = "yc_cpx"
        lfunc = "(main)"

    if g_loglevel > LL.INFO:
        dbxmod = '%s[%s:%s%s%s:%s] ' % (C.WHT, lmodname, C.YEL, lfunc, C.WHT, lline)
    else:
        dbxmod = ''

    finline = '%s%s<%s>%s %s%s\n' % (dbxmod, C.RED, LL.lname[loglevel], C.WHT, zline, C.OFF)

    # write log message
    if g_loglevel >= loglevel:
        sys.stdout.write(finline)

    if loglevel <= LL.ERROR:
        tstatus('error', msg="%s %s" % (logline, suffix))

def logexc(e, msg=None, prefix=None):
    """log exception"""
    if msg is not None:
        msg += ": "
    else:
        msg = "Exception logged"
    suffix = C.WHT + u"[" + C.YEL + str(e.__class__.__name__) + C.WHT + u"] " + C.YEL + str(e)
    logthis(msg, LL.ERROR, prefix, suffix)
    tstatus('exception', msg=msg, eclass=str(e.__class__.__name__), prefix=prefix)

def loglevel(newlvl=None):
    global g_loglevel
    if newlvl:
        g_loglevel = newlvl
    return g_loglevel

def failwith(etype, errmsg):
    logthis(errmsg, loglevel=LL.ERROR)
    tstatus('fail', etype=ER.lname[etype], msg=errmsg)

    raise xbError(etype)

def exceptionHandler(exception_type, exception, traceback):
    """exception handler callback"""
    # pylint: disable=unused-argument
    tstatus('exception', etype=exception_type.__name__, msg=exception)
    print("%s: %s" % (exception_type.__name__, exception))

def print_r(ind):
    """pretty-print a dict as JSON"""
    return json.dumps(ind, indent=4, separators=(',', ': '))

def tstatus(msgtype, **kwargs):
    """output json object with update data"""
    if _config['run']['tsukimi']:
        xout = {'msgtype': msgtype}
        xout.update(kwargs)
        sys.stderr.write(json.dumps(xout))
        sys.stderr.flush()

def configure_logging(xconfig):
    """store configuration for logging module"""
    global _config
    _config = xconfig
    loglevel(_config.core['loglevel'])
