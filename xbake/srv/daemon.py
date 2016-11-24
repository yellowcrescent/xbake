#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.srv.daemon
Daemon master process & REST API handler

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2016 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import sys
import os
import re
import time

from setproctitle import setproctitle
from flask import Flask, json, make_response, request

from xbake import __version__, __date__
from xbake.common.logthis import *
from xbake.mscan import out
from xbake.srv import queue

# XBake server Flask object
xsrv = None
config = None

# def start(bind_ip="0.0.0.0",bind_port=7037,fdebug=False):
def start(xconfig):
    """Start XBake Daemon"""
    global config, xsrv
    config = xconfig

    # first, fork
    if not config.srv['nofork']: dfork()

    # set process title
    setproctitle("xbake: master process (%s:%d)" % (config.srv['iface'], config.srv['port']))
    pidfile_set()

    # spawn queue runners
    queue.start(xconfig, 'xfer')
    queue.start(xconfig, 'xcode')

    # create flask object, and map API routes
    xsrv = Flask('xbake')
    xsrv.add_url_rule('/', 'root', view_func=route_root, methods=['GET'])
    xsrv.add_url_rule('/api/auth', 'auth', view_func=route_auth, methods=['GET', 'POST'])
    xsrv.add_url_rule('/api/mscan/add', 'mscan_add', view_func=route_mscan_add, methods=['GET', 'POST', 'PUT'])
    xsrv.add_url_rule('/api/mscan/getlast', 'mscan_last', view_func=route_mscan_last, methods=['GET', 'POST'])

    # start flask listener
    logthis("Starting Flask...", loglevel=LL.VERBOSE)
    xsrv.run(config.srv['iface'], config.srv['port'], config.srv['debug'], use_evalex=False)

def dfork():
    """Fork into the background"""
    logthis("Forking...", loglevel=LL.DEBUG)
    try:
        # first fork
        pid = os.fork()
    except OSError, e:
        logthis("os.fork() failed:", suffix=e, loglevel=LL.ERROR)
        failwith(ER.PROCFAIL, "Failed to fork into background. Aborting.")
    if (pid == 0):
        # become parent of session & process group
        os.setsid()
        try:
            # second fork
            pid = os.fork()
        except OSError, e:
            logthis("os.fork() [2] failed:", suffix=e, loglevel=LL.ERROR)
            failwith(ER.PROCFAIL, "Failed to fork into background. Aborting.")
        if pid:
            # ... and kill the other parent
            os._exit(0)

        logthis("** Forked into background. PID:", suffix=os.getpid(), loglevel=LL.INFO)
        # Redirect stdout & stderr to /dev/null
        sys.stdout.flush()
        sys.stdout = open(os.devnull, 'w')
        sys.stderr.flush()
        sys.stderr = open(os.devnull, 'w')
    else:
        # otherwise, kill the parent; _exit() so we don't mess with any
        # open file handles or streams; sleep for 0.5s to let the
        # "forked into background" message appear before the bash
        # prompt is given back to the user
        time.sleep(0.5)
        os._exit(0)

def dresponse(objx, rcode=200):
    """build standarized JSON response"""
    rx = make_response(pjson(objx), rcode)
    rx.headers['Content-Type'] = "application/json; charset=utf-8"
    rx.headers['Server'] = "XBake/"+__version__
    rx.headers['Accept'] = 'application/json'
    return rx

def precheck(rheaders=False, require_ctype=True):
    """
    Perform authorization and content-type checks before
    passing along a request to the destination route
    """
    # Check for proper Content-Type
    if require_ctype:
        try:
            ctype = request.headers['Content-Type']
        except KeyError:
            ctype = None
        if not re.match(r'^(application\/json|text\/x-json)', ctype, re.I):
            logthis("Content-Type mismatch. Not acceptable:", suffix=ctype, loglevel=LL.WARNING)
            if rheaders: return ({'status': "error", 'error': "json_required", 'message': "Content-Type must be application/json"}, "417 Content Mismatch")
            else: return False

    # Check authentication
    try:
        wauth = request.headers['WWW-Authenticate']
    except KeyError:
        wauth = None
    skey = config.srv['shared_key']
    if wauth:
        if wauth == skey:
            logthis("Authentication passed", loglevel=LL.VERBOSE)
            if rheaders: return ({'status': "ok"}, "212 Login Validated")
            else: return True
        else:
            logthis("Authentication failed; invalid credentials", loglevel=LL.WARNING)
            if rheaders: return ({'status': "error", 'error': "auth_fail", 'message': "Authentication failed"}, "401 Unauthorized")
            else: return False
    else:
        logthis("Authentication failed; WWW-Authenticate header missing from request", loglevel=LL.WARNING)
        if rheaders: return ({'status': "error", 'error': "www_authenticate_header_missing", 'message': "Must include WWW-Authenticate header"}, "400 Bad Request")
        else: return False

def route_root():
    """
    / [GET, POST]
    Return version information
    Does not require authentication
    """
    rinfo = {
                'app': "XBake",
                'description': "Media scanner, transcoder, and generally-handy subtitle baker thing",
                'version': __version__,
                'date': __date__,
                'author': "J. Hipps <jacob@ycnrg.org>",
                'copyright': "Copyright (c) 2013-2016 J. Hipps/Neo-Retro Group, Inc.",
                'license': "MIT"
            }
    return dresponse(rinfo)

def route_auth():
    """
    /api/auth [GET, POST]
    Check authentication credentials
    """
    return dresponse(*precheck(rheaders=True))

def route_mscan_add():
    """
    /mscan/add [PUT, POST]
    Add new file(s) to the database from a recent scan
    This receives the full scan results from a recent run of `xbake --mscan`
    as JSON data
    """
    logthis(">> Received mscan_add request", loglevel=LL.VERBOSE)

    if precheck():
        # Write to Mongo
        cmon = config.mongo
        xstatus = out.to_mongo(request.json, cmon)
        hcode = xstatus['http_status']
        del(xstatus['http_status'])
        resp = dresponse(xstatus, hcode)
    else:
        resp = dresponse(*precheck(rheaders=True))

    return resp

def route_mscan_last():
    """
    /mscan/getlast [GET]
    Retrieve the most recent scan results from the database
    """
    return dresponse(None, '501 Not Implemented')

def pjson(oin):
    """prettify json"""
    return json.dumps(oin, indent=4, separators=(',', ': '))

def pidfile_set():
    """
    create/update pidfile to config.srv.pidfile
    """
    pfname = config.srv['pidfile']
    try:
        fo = open(pfname, "w")
        fo.write("%d\n" % os.getpid())
        fo.close()
    except Exception as e:
        logexc(e, "Failed to write data to PID file (%s)" % (pfname))
        failwith(ER.PROCFAIL, "Ensure write permission at the PID file location.")
