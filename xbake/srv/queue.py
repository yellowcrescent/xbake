#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.srv.queue
Queue Runner

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2016 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import sys
import os
import re
import json
import subprocess
import pipes

from setproctitle import setproctitle

from xbake.common.logthis import *
from xbake.common import db
from xbake.mscan.util import md5sum, dstat
from xbake.xcode import xcode

# Queue handler callbacks
handlers = None

# Host metrics and encode profiles
hmetrics = None
xprofiles = None

# Redis & Mongo objects; Parent PID
rdx = None
mdx = None
dadpid = None
config = None

def start(xconfig, qname="xcode"):
    """
    fork queue runner for queue @qname
    """
    global rdx, mdx, dadpid, handlers, hmetrics, xprofiles, config

    # Fork into its own process
    logthis("Forking...", loglevel=LL.DEBUG)
    dadpid = os.getpid()
    try:
        pid = os.fork()
    except OSError, e:
        logthis("os.fork() failed:", suffix=e, loglevel=LL.ERROR)
        failwith(ER.PROCFAIL, "Failed to fork worker. Aborting.")

    # Return if we are the parent process
    if pid:
        return 0

    # Otherwise, we are the child
    logthis("Forked queue runner. pid =", prefix=qname, suffix=os.getpid(), loglevel=LL.INFO)
    logthis("QRunner. ppid =", prefix=qname, suffix=dadpid, loglevel=LL.VERBOSE)
    setproctitle("xbake: queue runner - %s" % (qname))

    config = xconfig

    # Connect to Redis
    rdx = db.redis({'host': config.redis['host'], 'port': config.redis['port'], 'db': config.redis['db']}, prefix=config.redis['prefix'])

    # Connect to Mongo
    mdx = db.mongo(config.mongo)

    # Set queue callbacks
    handlers = {
                 'xfer': cb_xfer,
                 'xcode': cb_xcode
               }

    # Get host metrics
    hmetrics = load_metrics()

    # Get xcode profiles
    xprofiles = load_profiles()

    # Start listener loop
    qrunner(qname)

    # And exit once we're done
    logthis("*** Queue runner terminating", prefix=qname, loglevel=LL.INFO)
    sys.exit(0)

def qrunner(qname="xcode"):
    """
    Queue runner main loop
    """
    global rdx, mdx, handlers

    qq = "queue_"+qname
    wq = "work_"+qname

    # Crash recovery
    # Check work queue (work_*) and re-queue any unhandled items
    logthis("-- QRunner crash recovery: checking for abandoned jobs...", loglevel=LL.VERBOSE)
    requeued = 0
    while(rdx.llen(wq) != 0):
        crraw = rdx.lpop(wq)
        try:
            critem = json.loads(crraw)
        except Exception as e:
            logthis("!! QRunner crash recovery: Bad JSON data from queue item. Job discarded. raw data:", prefix=qname, suffix=crraw, loglevel=LL.ERROR)
            logexc(e, "Error loading JSON data")
            continue
        cr_jid = critem.get("id", "??")
        logthis("** Requeued abandoned job:", prefix=qname, suffix=cr_jid, loglevel=LL.WARNING)
        rdx.rpush(qq, crraw)
        requeued += 1

    if requeued:
        logthis("-- QRunner crash recovery OK! Jobs requeued:", prefix=qname, suffix=requeued, loglevel=LL.VERBOSE)

    logthis("pre-run queue sizes: %s = %d / %s = %d" % (qq, rdx.llen(qq), wq, rdx.llen(wq)), prefix=qname, loglevel=LL.DEBUG)
    logthis("-- QRunner waiting; queue:", prefix=qname, suffix=qname, loglevel=LL.VERBOSE)
    while(True):
        # RPOP from main queue and LPUSH on to the work queue
        # block for 5 seconds, check that the master hasn't term'd, then
        # check again until we get something
        qitem = None
        qiraw = rdx.brpoplpush(qq, wq, 5)
        if qiraw:
            logthis(">> QRunner: discovered a new job in queue", prefix=qname, suffix=qname, loglevel=LL.VERBOSE)

            try:
                qitem = json.loads(qiraw)
            except Exception as e:
                logthis("!! QRunner: Bad JSON data from queue item. Job discarded. raw data:", prefix=qname, suffix=qiraw, loglevel=LL.ERROR)

            # If we've got a valid job item, let's run it!
            if qitem:
                logthis(">> QRunner: job data:\n", prefix=qname, suffix=json.dumps(qitem), loglevel=LL.DEBUG)

                # Execute callback
                rval = handlers[qname](qitem)
                if (rval == 0):
                    logthis("QRunner: Completed job successfully.", prefix=qname, loglevel=LL.VERBOSE)
                elif (rval == 1):
                    logthis("QRunner: Job complete, but with warnings.", prefix=qname, loglevel=LL.WARNING)
                else:
                    logthis("QRunner: Job failed. rval =", prefix=qname, suffix=rval, loglevel=LL.ERROR)

                # Remove from work queue
                rdx.rpop(wq)

            # Show wait message again
            logthis("-- QRunner: waiting; queue:", prefix=qname, suffix=qname, loglevel=LL.VERBOSE)

        # Check if daddy is still alive; prevents this process from becoming a bastard child
        if not master_alive():
            logthis("QRunner: Master has terminated.", prefix=qname, loglevel=LL.WARNING)
            return

def cb_xfer(jdata):
    """
    Job processor for xfer queue (callback)
    Determines host with lowest metric (if file is on multiple hosts), then calls
    scp to copy the file to the new host
    @jdata {jid, fid, opts: {infile, realpath, basefile, location, ...}}
    """
    global mdx, hmetrics, config
    xfer_loc = config.srv['xfer_path'].rstrip('/')

    # get options from job request
    jid = jdata['id']
    fid = jdata['fid']
    opts = jdata['opts']

    # retrieve from Mongo
    fvid = mdx.findOne('files', {"_id": fid})
    oneloc = fvid['location'].keys()[0]
    expect_file = fvid['location'][oneloc]['fpath']['file']

    # Do some loggy stuff
    logthis("xfer: JobID %s / FileID %s / Opts %s" % (jid, fid, json.dumps(opts)), loglevel=LL.VERBOSE)
    logthis("xfer: Filename:", suffix=expect_file, loglevel=LL.VERBOSE)
    logthis("xfer: Locations:", suffix=json.dumps(fvid['location'].keys()), loglevel=LL.DEBUG)

    # check if file already exists on the server
    xfname = xfer_loc + "/" + expect_file
    if check_file_exists(xfname, fvid['checksum']['md5']):
        logthis("xfer: File already exists in destination path with matching checksum.", loglevel=LL.WARNING)
        update_status(fid, "queued-xcode")
        opts['infile'] = fvid['location'][oneloc]['fpath']['file']
        opts['basefile'] = fvid['location'][oneloc]['fpath']['base']
        opts['location'] = oneloc
        opts['realpath'] = xfname
        enqueue('xcode', jid, fid, opts)
        return 0

    # determine location with lowest metric (if multiple locations present)
    lbest = (None, None)
    for ttl in fvid['location'].keys():
        cmetric = hmetrics.get(ttl, 100)
        if lbest[1] is None or cmetric < lbest[1]:
            lbest = (ttl, cmetric)

    bestloc = lbest[0]
    logthis("xfer: Chose location %s, metric %d" % lbest, loglevel=LL.VERBOSE)

    # set download location
    dloc = fvid['location'][bestloc]
    xrem_host = bestloc.replace('_', '.')

    # connect using only the host portion of the FQDN
    # if srv.xfer_hostonly option is enabled
    if config.srv['xfer_hostonly']:
        try:
            r_host = re.match(r'^([^\.]+)\.', xrem_host).group(1)
            logthis("xfer: Using hostname for ssh connection:", suffix=r_host, loglevel=LL.VERBOSE)
        except:
            logthis("xfer: Failed to parse host portion of fully-qualified hostname:", suffix=xrem_host, loglevel=LL.ERROR)
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
    xsrc_path = "%s:%s" % (r_host, pipes.quote(r_path))
    xdest_path = pipes.quote(l_path + "/")
    logthis(">> Starting transfer: %s -> %s (%d bytes)" % (r_path, l_real, r_size), loglevel=LL.VERBOSE)
    update_status(fid, "downloading")
    scp(xsrc_path, xdest_path)

    # check the file to ensure it exists and is the correct size
    if check_file_xfer(l_real, r_size):
        logthis("Complete: File transfer successful!", loglevel=LL.VERBOSE)
        update_status(fid, "queued-xcode")
        enqueue('xcode', jid, fid, opts)
        return 0
    else:
        logthis("Error: File transfer failed", loglevel=LL.ERROR)
        update_status(fid, "new")
        return 101


def cb_xcode(jdata):
    """
    Job processor for xcode queue (callback)
    Uses information from the request, as well as current settings and defaults to determine
    transcoding parameters. Then xcode.run() is called to handle transcoding via FFmpeg
    @jdata {jid, fid, opts: {profile, version, realpath, basefile, location, no_subs, vscap, fansub, ...}}
    """
    global mdx, xprofiles, config

    # get global options
    outpath = os.path.expanduser(config.srv['xcode_outpath']).rstrip("/")
    s_allow = int(config.srv['xcode_scale_allowance'])

    # get options from job request
    jid = jdata['id']
    fid = jdata['fid']
    opts = jdata['opts']

    # set profile & version
    xprof = opts.get('profile', config.srv['xcode_default_profile']).lower()
    vname = opts.get('version', xprof)
    profdata = xprofiles.get(xprof, {})

    # build file paths
    f_in = opts['realpath']
    if vname:
        f_out = outpath + "/" + vname + "/" + opts['basefile'] + ".mp4"
    else:
        f_out = outpath + "/" + opts['basefile'] + ".mp4"

    # retrieve file entry from Mongo
    fvid = mdx.findOne('files', {"_id": fid})
    oneloc = fvid['location'].keys()[0]
    expect_file = fvid['location'][oneloc]['fpath']['file']  #pylint: disable=unused-variable

    # Do some loggy stuff
    logthis("xcode: JobID %s / FileID %s / Opts %s" % (jid, fid, json.dumps(opts)), loglevel=LL.VERBOSE)
    logthis("xcode: Input file:", suffix=f_in, loglevel=LL.VERBOSE)
    logthis("xcode: Output file:", suffix=f_out, loglevel=LL.VERBOSE)
    logthis("xcode: Version:", suffix=vname, loglevel=LL.VERBOSE)
    logthis("xcode: Profile:", suffix=xprof, loglevel=LL.VERBOSE)
    logthis("xcode: Profile data:", suffix=json.dumps(profdata), loglevel=LL.DEBUG)

    # Create new XConfig instance
    newconf = config._clone()

    ## Set encoding options
    if newconf.core['loglevel'] > LL.VERBOSE:
        newconf.xcode['show_ffmpeg'] = True
    else:
        newconf.xcode['show_ffmpeg'] = newconf.srv['xcode_show_ffmpeg']

    # Set File, ID, and Version info
    newconf.run['infile'] = f_in
    newconf.run['outfile'] = f_out
    newconf.run['id'] = fid
    newconf.vid['location'] = opts['location']
    newconf.vid['vername'] = vname

    # Audio options
    newconf.xcode['acopy'] = 'auto'
    newconf.xcode['downmix'] = 'auto'
    newconf.xcode['abr'] = int(profdata.get('abr', 128))

    # Subtitle options
    if not opts.get('no_subs', False):
        newconf.run['bake'] = True
        newconf.xcode['subid'] = 'auto'
    else:
        newconf.run['bake'] = False

    # Screenshot options
    if opts.get('vscap', 0):
        newconf.run['vscap'] = opts['vscap']
    elif int(opts.get('vscap', 0)) == -1:
        newconf.run['vscap'] = False
    else:
        # If no vscap offset is set, then take the 3rd chapter offset and add 5 seconds
        # If no 3rd chapter, 440 seconds? go!
        try:
            zoff = int(fvid['mediainfo']['menu'][2]['offset']) + 5
        except:
            zoff = 440
        newconf.run['vscap'] = zoff

    # Metadata options
    if opts.get('fansub', False):
        newconf.run['fansub'] = opts['fansub']
    else:
        newconf.run['fansub'] = None

    ## Video options
    newconf.xcode['crf'] = int(profdata.get('crf', config.xcode['crf']))

    # Performing scaling to match profile, if necessary
    xscale = False
    if profdata.get('height', False):
        # Get source size and AR
        v_width = int(fvid['mediainfo']['video'][0].get('width', 0))
        v_height = int(fvid['mediainfo']['video'][0].get('height', 0))
        v_ar, v_iar, v_dar = get_aspect(fvid['mediainfo']['video'][0])  #pylint: disable=unused-variable

        # calculate expected/target size
        x_height = int(profdata['height'])
        x_width = int(float(profdata['height']) * v_iar)

        # check if we need to scale
        if v_height < (x_height - s_allow) or v_height > (x_height + s_allow): xscale = True
        if v_width < (x_width - s_allow) or v_width > (x_width + s_allow): xscale = True

        # make sure to scale if the source video has an uneven dimension (as required by x264)
        if (v_height % 2) or (v_width % 2): xscale = True

    # set scale params
    if xscale:
        if v_ar == profdata.get('aspect', 0) and profdata.get('width', False):
            s_width = int(profdata['width'])
        else:
            s_width = x_width
        # ensure s_width is always even
        s_width += s_width % 2
        newconf.xcode['scale'] = "%d:%d" % (s_width, x_height)
    else:
        newconf.xcode['scale'] = None

    # print params for debugging
    logthis("xcode: Set xsetup.xcode newconf:\n", suffix=str(newconf.xcode), loglevel=LL.DEBUG)
    logthis("xcode: Set xsetup.run newconf:\n", suffix=str(newconf.run), loglevel=LL.DEBUG)
    logthis("xcode: Set xsetup.vid newconf:\n", suffix=str(newconf.vid), loglevel=LL.DEBUG)

    # Transcode
    logthis("xcode: Handing off control to xbake.xcode module for transcoding.", loglevel=LL.VERBOSE)
    update_status(fid, "transcoding")
    xcode.run(newconf)

    # Check for presence of output file
    if not os.path.exists(f_out):
        logthis("xcode: Output file not found. Transcoding failed.", loglevel=LL.ERROR)
        update_status(fid, "new", lerror="transcoding failed")
        return 121
    else:
        logthis("xcode: Transcoding completed successfully", loglevel=LL.VERBOSE)
        update_status(fid, "complete")
        return 0

def get_aspect(midata):
    """
    calculate aspect ratio from mediainfo data @midata
    returns: tuple (fraction_string, float, rounded)
    """
    smap = {1.78: "16:9", 1.5: "3:2", 1.33: "4:3", 1.25: "5:4"}
    # get aspect ratio reported in metadata
    iar = midata.get('display_aspect_ratio', midata.get('aspect', round(float(midata['width']) / float(midata['height']), 2)))
    if iar.count(':'):
        iar = float(iar.split(':')[0]) / float(iar.split(':')[1])
        dar = round(iar, 2)
    else:
        iar = float(iar)
        dar = round(iar, 2)
    return (smap.get(dar, str(dar)), iar, dar)

def scp(src, dest):
    """
    executes scp to perform a transfer
    @src and @dest should contain host:path
    """
    try:
        subprocess.check_output(['/usr/bin/scp', '-B', '-r', src, dest])
        return True
    except subprocess.CalledProcessError as e:
        logthis("Error: scp returned non-zero.", suffix=e, loglevel=LL.ERROR)
        return False

def enqueue(qname, jid, fid, opts, silent=False):
    """
    create a new job in queue (@qname), with job ID (@jid), file ID (@fid), and options (@opts)
    """
    global rdx
    rdx.lpush("queue_"+qname, json.dumps({'id': jid, 'fid': fid, 'opts': opts}))
    if not silent: logthis("Enqueued job# %s in queue:" % (jid), suffix=qname, loglevel=LL.VERBOSE)

def master_alive():
    """
    check if master process is alive
    returns True if alive, False otherwise
    """
    global dadpid
    try:
        os.kill(dadpid, 0)
    except OSError:
        return False
    else:
        return True

def update_status(fid, status, lerror=None):
    """
    update status of file (@fid) with @status
    """
    global mdx
    if lerror: mdx.update_set('files', fid, {'status': status, 'last-error': lerror})
    else: mdx.update_set('files', fid, {'status': status})

def check_file_xfer(freal, fsize):
    """
    determine if a file has been transferred
    returns True if file exists and is correct size, False otherwise
    """
    if os.path.exists(freal):
        truesize = dstat(freal)['size']
        if truesize == fsize:
            return True
        else:
            logthis("%s - Size mismatch: Expected %d bytes, got" % (freal, fsize), suffix=truesize, loglevel=LL.ERROR)
            return False
    else:
        return False

def check_file_exists(fname, chksum=False):
    """
    determine if a file already exists at destination; optionally, if @chksum=True,
    then the MD5 checksum will be checked against the record in the database to ensure they match
    returns True if file exists, False otherwise
    """
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
    """
    Load metrics from [hosts] section of RC file
    """
    global config
    if 'hosts' in config:
        mets = config.hosts
    else:
        mets = {}
    mets2 = {}
    for tm in mets:
        try:
            mets2[tm.replace('.', '_')] = int(mets[tm])
        except:
            logthis("Bad hostline for", suffix=tm, loglevel=LL.ERROR)

    logthis("Host metric list:\n", suffix=print_r(mets2), loglevel=LL.DEBUG)
    return mets2

def load_profiles():
    """
    Load encoding profiles from [profiles] section of RC file
    """
    global config
    if 'profiles' in config:
        profs = config.profiles
    else:
        profs = {}
    oplist = {}
    for tp in profs:
        xlist = {}
        try:
            for tox in profs[tp].split(','):
                k, v = tox.split('=')
                xlist[k.lower()] = v
            oplist[tp] = xlist
        except Exception as e:
            logthis("Failed to parse profile for", suffix=tp, loglevel=LL.ERROR)
            logthis("Error:", suffix=e, loglevel=LL.ERROR)

    logthis("Parsed xcode profiles:\n", suffix=print_r(oplist), loglevel=LL.DEBUG)
    return oplist
