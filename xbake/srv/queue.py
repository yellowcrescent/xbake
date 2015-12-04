#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# queue - xbake/srv/queue.py
# XBake: Queue Runner
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
import json
from setproctitle import setproctitle
from xbake.common import db

# Logging & Error handling
from xbake.common.logthis import C,LL,ER,logthis,failwith,print_r

# Redis object
rdx = None
dadpid = None

def start():
    global rdx, dadpid

    # Fork into its own process
    logthis("Forking...",loglevel=LL.DEBUG)
    dadpid = os.getpid()
    try:
        pid = os.fork()
    except OSError, e:
        logthis("os.fork() failed:",suffix=e,loglevel=LL.ERROR)
        failwith(ER.PROCFAIL, "Failed to fork worker. Aborting.")

    # Return if we are the parent process
    if pid:
        return 0

    # Otherwise, we are the child
    logthis("Forked queue runner. pid =",suffix=os.getpid(),loglevel=LL.INFO)
    logthis("QRunner. ppid =",suffix=dadpid,loglevel=LL.VERBOSE)
    setproctitle("yc_xbake: queue runner - xcode")

    conf = __main__.xsetup.config

    # Connect to Redis
    rdx = db.redis({ 'host': conf['redis']['host'], 'port': conf['redis']['port'], 'db': conf['redis']['db'] },prefix=conf['redis']['prefix'])

    # Start listener loop
    qrunner()
    logthis("*** Queue runner terminating",loglevel=LL.INFO)
    sys.exit(0)

def master_alive():
    global dadpid
    try:
        os.kill(dadpid, 0)
    except OSError:
        return False
    else:
        return True

def qrunner(qname="xcode"):
    global rdx

    qq = "queue_"+qname
    wq = "work_"+qname

    logthis("-- QRunner waiting; queue:",suffix=qname,loglevel=LL.VERBOSE)
    while(True):
        # RPOP from main queue and LPUSH on to the work queue
        # block until we receive something in the queue
        qitem = None
        qiraw = rdx.brpoplpush(qq,wq,5)
        if qiraw:
            logthis(">> QRunner: discovered a new job in queue",suffix=qname,loglevel=LL.VERBOSE)

            try:
                qitem = json.loads(qiraw)
            except e:
                logthis("!! QRunner: Bad JSON data from queue item. Job discarded. raw data:",suffix=qiraw,loglevel=LL.ERROR)

            # If we've got a valid job item, let's run it!
            if qitem:
                logthis(">> QRunner: job data:\n",suffix=json.dumps(qitem),loglevel=LL.DEBUG)

                # Remove from work queue
                rdx.rpop(wq)

            # Show wait message again
            logthis("-- QRunner: waiting; queue:",suffix=qname,loglevel=LL.VERBOSE)

        # Check if daddy is still alive; prevents this process from becoming a bastard child
        if not master_alive():
            logthis("QRunner: Master has terminated.",loglevel=LL.WARNING)
            return


