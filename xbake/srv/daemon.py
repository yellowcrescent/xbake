#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# daemon - xbake/srv/daemon.py
# XBake: API Service Daemon
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_xbake
#
# Copyright (c) 2015 J. Hipps / Neo-Retro Group
#
# https://ycnrg.org/
#
###############################################################################

import __main__
import sys
import os
import re
import signal
import time
from flask import Flask,json,jsonify,make_response,request

# Logging & Error handling
from xbake.common.logthis import C,LL,ER,logthis,failwith,print_r

# XBake server Flask object
xsrv = None

def start(bind_ip="0.0.0.0",bind_port=7037,fdebug=False):
    """Start XBake Daemon"""
    conf = __main__.xsetup.config
    #shared_key = conf['srv']['shared_key']
    #logthis(">> Shared Key",suffix=shared_key,loglevel=LL.DEBUG)

    # first, fork
    if not conf['srv']['nofork']: dfork()

    # create flask object, and map API routes
    xsrv = Flask('xbake')
    xsrv.add_url_rule('/','root',view_func=route_root,methods=['GET'])
    xsrv.add_url_rule('/api/auth','auth',view_func=route_auth,methods=['GET','POST'])
    xsrv.add_url_rule('/api/mscan/add','mscan_add',view_func=route_mscan_add,methods=['GET','POST','PUT'])
    xsrv.add_url_rule('/api/mscan/getlast','mscan_last',view_func=route_mscan_last,methods=['GET','POST'])

    # start flask listener
    logthis("Starting Flask...",loglevel=LL.VERBOSE)
    xsrv.run(bind_ip,bind_port,fdebug,use_evalex=False)

def dfork():
    """Fork into the background"""
    logthis("Forking...",loglevel=LL.DEBUG)
    try:
        # first fork
        pid = os.fork()
    except OSError, e:
        logthis("os.fork() failed:",suffix=e,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL, "Failed to fork into background. Aborting.")
    if (pid == 0):
        # become parent of session & process group
        os.setsid()
        try:
            # second fork
            pid = os.fork()
        except OSError, e:
            logthis("os.fork() [2] failed:",suffix=e,loglevel=LL.ERROR)
            failwith(ER.PROCFAIL, "Failed to fork into background. Aborting.")
        if pid:
            # ... and kill the other parent
            os._exit(0)

        logthis("** Forked into background. PID:",suffix=os.getpid(),loglevel=LL.INFO)
        # Redirect stdout & stderr to /dev/null
        sys.stdout.flush()
        sys.stdout = open(os.devnull,'w')
        sys.stderr.flush()
        sys.stderr = open(os.devnull,'w')
    else:
        # otherwise, kill the parent; _exit() so we don't mess with any
        # open file handles or streams; sleep for 0.5s to let the
        # "forked into background" message appear before the bash
        # prompt is given back to the user
        time.sleep(0.5)
        os._exit(0)

def dresponse(objx,rcode=200):
    rx = make_response(pjson(objx),rcode)
    rx.headers['Content-Type'] = "application/json; charset=utf-8"
    rx.headers['Server'] = "XBake/"+__main__.xsetup.version
    rx.headers['Accept'] = 'application/json'
    return rx

def route_root():
    rinfo = {
                'app': "XBake",
                'description': "Media scanner, transcoder, and generally-handy subtitle baker thing",
                'version': __main__.xsetup.version,
                'date': __main__.xsetup.vdate,
                'author': "J. Hipps <jacob@ycnrg.org>",
                'copyright': "Copyright (c) 2013-2015 J. Hipps/Neo-Retro Group",
                'license': "MIT"
            }
    return dresponse(rinfo)

def route_auth():
    try:
        wauth = request.headers['WWW-Authenticate']
    except KeyError:
        wauth = None
    skey = __main__.xsetup.config['srv']['shared_key']
    if wauth:
        if wauth == skey:
            resp = dresponse({ 'status': "OK" },202)
        else:
            resp = dresponse({ 'status': "AUTH FAIL" },401)
    else:
        resp = dresponse({ 'error': "Must include WWW-Authenticate header" },400)

    return resp

def route_mscan_add():
    return dresponse(rinfo)

def route_mscan_last():
    return dresponse(rinfo)

def pjson(oin):
    return json.dumps(oin,indent=4,separators=(',', ': '))
