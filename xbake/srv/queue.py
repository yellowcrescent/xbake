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
import subprocess
import pipes
from setproctitle import setproctitle
from xbake.common import db

# Logging & Error handling
from xbake.common.logthis import C,LL,ER,logthis,failwith,print_r

# MScan and other file utility imports
from xbake.mscan.util import md5sum,checksum,rhash,dstat

# Queue handler callbacks
handlers = None

# Host metrics
hmetrics = None

# Redis & Mongo objects; Parent PID
rdx = None
mdx = None
dadpid = None

def start(qname="xcode"):
    global rdx, mdx, dadpid, handlers, hmetrics

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
    logthis("Forked queue runner. pid =",prefix=qname,suffix=os.getpid(),loglevel=LL.INFO)
    logthis("QRunner. ppid =",prefix=qname,suffix=dadpid,loglevel=LL.VERBOSE)
    setproctitle("yc_xbake: queue runner - %s" % (qname))

    conf = __main__.xsetup.config

    # Connect to Redis
    rdx = db.redis({ 'host': conf['redis']['host'], 'port': conf['redis']['port'], 'db': conf['redis']['db'] },prefix=conf['redis']['prefix'])

    # Connect to Mongo
    mdx = db.mongo(conf['mongo'])

    # Set queue callbacks
    handlers = {
                 'xfer': cb_xfer,
                 'xcode': cb_xcode
               }

    # Get host metrics
    hmetrics = load_metrics()

    # Start listener loop
    qrunner(qname)

    # And exit once we're done
    logthis("*** Queue runner terminating",prefix=qname,loglevel=LL.INFO)
    sys.exit(0)

def qrunner(qname="xcode"):
    global rdx, mdx, handlers

    qq = "queue_"+qname
    wq = "work_"+qname

    # TODO: check work queue (work_*) and process any unhandled items

    logthis("-- QRunner waiting; queue:",prefix=qname,suffix=qname,loglevel=LL.VERBOSE)
    while(True):
        # RPOP from main queue and LPUSH on to the work queue
        # block for 5 seconds, check that the master hasn't term'd, then
        # check again until we get something
        qitem = None
        qiraw = rdx.brpoplpush(qq,wq,5)
        if qiraw:
            logthis(">> QRunner: discovered a new job in queue",prefix=qname,suffix=qname,loglevel=LL.VERBOSE)

            try:
                qitem = json.loads(qiraw)
            except e:
                logthis("!! QRunner: Bad JSON data from queue item. Job discarded. raw data:",prefix=qname,suffix=qiraw,loglevel=LL.ERROR)

            # If we've got a valid job item, let's run it!
            if qitem:
                logthis(">> QRunner: job data:\n",prefix=qname,suffix=json.dumps(qitem),loglevel=LL.DEBUG)

                # Execute callback
                rval = handlers[qname](qitem)
                if (rval == 0):
                    logthis("QRunner: Completed job successfully.",prefix=qname,loglevel=LL.VERBOSE)
                elif (rval == 1):
                    logthis("QRunner: Job complete, but with warnings.",prefix=qname,loglevel=LL.WARNING)
                else:
                    logthis("QRunner: Job failed. rval =",prefix=qname,suffix=rval,loglevel=LL.ERROR)

                # Remove from work queue
                rdx.rpop(wq)

            # Show wait message again
            logthis("-- QRunner: waiting; queue:",prefix=qname,suffix=qname,loglevel=LL.VERBOSE)

        # Check if daddy is still alive; prevents this process from becoming a bastard child
        if not master_alive():
            logthis("QRunner: Master has terminated.",prefix=qname,loglevel=LL.WARNING)
            return

def cb_xfer(jdata):
    global mdx, hmetrics
    xfer_loc = __main__.xsetup.config['srv']['xfer_path'].rstrip('/')

    # get options from job request
    jid  = jdata['id']
    fid  = jdata['fid']
    opts = jdata['opts']

    # retrieve from Mongo
    fvid = mdx.findOne('files',{ "_id": fid })
    oneloc = fvid['location'].keys()[0]
    expect_file = fvid['location'][oneloc]['fpath']['file']

    # Do some loggy stuff
    logthis("xfer: JobID %s / FileID %s / Opts %s" % (jid,fid,json.dumps(opts)),loglevel=LL.VERBOSE)
    logthis("xfer: Filename:",suffix=expect_file,loglevel=LL.VERBOSE)
    logthis("xfer: Locations:",suffix=json.dumps(fvid['location'].keys()),loglevel=LL.DEBUG)

    # check if file already exists on the server
    xfname = xfer_loc + "/" + expect_file
    if check_file_exists(xfname, fvid['checksum']['md5']):
        logthis("xfer: File already exists in destination path with matching checksum.",loglevel=LL.WARNING)
        update_status(fid, "queued-xcode")
        opts['infile'] = fvid['location'][oneloc]['fpath']['file']
        opts['basefile'] = fvid['location'][oneloc]['fpath']['base']
        opts['location'] = oneloc
        opts['realpath'] = xfname
        enqueue('xcode', jid, fid, opts)
        return 0

    # determine location with lowest metric (if multiple locations present)
    lbest = False
    for ttl in fvid['location'].keys():
        cmetric = hmetrics.get(ttl,100)
        if (not lbest) or (cmetric < lbest[1]):
            lbest = (ttl, cmetric)

    bestloc = lbest[0]
    logthis("xfer: Chose location %s, metric %d" % (lbest),loglevel=LL.VERBOSE)

    # set download location
    dloc = fvid['location'][bestloc]
    xrem_host = bestloc.replace('_','.')

    # connect using only the host portion of the FQDN
    # if srv.xfer_hostonly option is enabled
    if __main__.xsetup.config['srv']['xfer_hostonly']:
        try:
            r_host = re.match("^([^\.]+)\.",xrem_host).group(1)
            logthis("xfer: Using hostname for ssh connection:",suffix=r_host,loglevel=LL.VERBOSE)
        except:
            logthis("xfer: Failed to parse host portion of fully-qualified hostname:",suffix=xrem_host,loglevel=LL.ERROR)
            r_host = xrem_host
    else:
        r_host = xrem_host

    # get remote and local paths and recorded filesize
    r_size = dloc['stat']['size']
    r_path = dloc['fpath']['real']
    l_path = xfer_loc
    l_real = l_path + "/" + dloc['fpath']['file']

    # set options for next job
    opts['infile'] = dloc['fpath']['file']
    opts['basefile'] = dloc['fpath']['base']
    opts['location'] = bestloc
    opts['realpath'] = l_real

    # run scp
    xsrc_path  = "%s:%s" % (r_host, pipes.quote(r_path))
    xdest_path = pipes.quote(l_path + "/")
    logthis(">> Starting transfer: %s -> %s (%d bytes)" % (r_path,l_real,r_size),loglevel=LL.VERBOSE)
    update_status(fid, "downloading")
    scp(xsrc_path, xdest_path)

    # check the file to ensure it exists and is the correct size
    if check_file_xfer(l_real, r_size):
        logthis("Complete: File transfer successful!",loglevel=LL.VERBOSE)
        update_status(fid, "queued-xcode")
        enqueue('xcode', jid, fid, opts)
        return 0
    else:
        logthis("Error: File transfer failed",loglevel=LL.ERROR)
        update_status(fid, "new")
        return 101


def cb_xcode(jdata):
    global mdx

    # get options from job request
    jid  = jdata['id']
    fid  = jdata['fid']
    opts = jdata['opts']

    #### TESTING STUB ####
    update_status(fid, "new")
    return 0

def scp(src,dest):
    try:
        subprocess.check_output(['/usr/bin/scp','-B','-r',src,dest])
        return True
    except subprocess.CalledProcessError as e:
        logthis("Error: scp returned non-zero.",suffix=e,loglevel=LL.VERBOSE)
        return False

def enqueue(qname,jid,fid,opts,silent=False):
    global rdx
    rdx.lpush("queue_"+qname, json.dumps({'id': jid, 'fid': fid, 'opts': opts }))
    if not silent: logthis("Enqueued job# %s in queue:" % (jid),suffix=qname,loglevel=LL.VERBOSE)

def master_alive():
    global dadpid
    try:
        os.kill(dadpid, 0)
    except OSError:
        return False
    else:
        return True

def update_status(fid,status,lerror=None):
    global mdx
    if lerror: mdx.update_set('files', fid, {'status': status, 'last-error': lerror})
    else: mdx.update_set('files', fid, {'status': status})

def check_file_xfer(freal,fsize):
    if os.path.exists(freal):
        truesize = dstat(freal)['size']
        if truesize == fsize:
            return True
        else:
            logthis("%s - Size mismatch: Expected %d bytes, got" % (freal,fsize),suffix=truesize,loglevel=LL.ERROR)
            return False
    else:
        return False

def check_file_exists(fname,chksum=False):
    if os.path.exists(fname) and os.path.isfile(fname):
        if chksum:
            if md5sum(fname) == chksum:
                return True
            else:
                return False
        else:
            return True
    else:
        return False

def load_metrics():
    # Load metrics from [hosts] section of RC file
    mets = __main__.xsetup.config.get('hosts',{})
    mets2 = {}
    for tm in mets:
        try:
            mets2[tm.replace('.','_')] = int(mets[tm])
        except:
            logthis("Bad hostline for",suffix=tm,loglevel=LL.ERROR)

    logthis("Host metric list:\n",suffix=print_r(mets2),loglevel=LL.DEBUG)

    return mets2
