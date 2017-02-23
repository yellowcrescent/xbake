#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.cli
Command-line interface & arg parsing

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

from __future__ import print_function

import sys
import os
import optparse

from xbake import __version__, __date__, defaults
from xbake.common.logthis import *
from xbake.common import rcfile
from xbake.xcode import ffmpeg, xcode, ssonly
from xbake.mscan import mscan, scrapers
from xbake.srv import daemon
from xbake import ascan

oparser = None

def show_banner():
    """
    Display banner
    """
    print("")
    print(C.CYN, "*** ", C.WHT, "XBake", C.OFF)
    print(C.CYN, "*** ", C.CYN, "Version", __version__, "(" + __date__ + ")", C.OFF)
    print(C.CYN, "*** ", C.GRN, "Copyright (c) 2013-2017 Jacob Hipps <jacob@ycnrg.org>", C.OFF)
    print(C.CYN, "*** ", C.GRN, "RHash & librhash, Copyright (c) 2011-2012 Sergey Basalaev & Aleksey Kravchenko <http://rhash.anz.ru/>", C.OFF)
    print(C.CYN, "*** ", C.YEL, "https://ycnrg.org/", C.OFF)
    print("")

def parse_cli():
    """
    Parse command-line options
    """
    global oparser
    oparser = optparse.OptionParser(usage="%prog <--xcode|--scan|--ascan|--ssonly|--server|--set> [options] <[-i] INFILE> [[-o] OUTFILE]", version=__version__+" ("+__date__+")")

    # General options
    oparser.add_option('-v', '--verbose', action="count", dest="run.verbose", help="Increase logging verbosity (-v Verbose, -vv Debug, -vvv Debug2)")
    oparser.add_option('-q', '--quiet', action="store_true", dest="run.quiet", help="Silence all log output except critial errors")
    oparser.add_option('-L', '--loglevel', action="store", dest="core.loglevel", default=False, metavar="NUM", help="Logging output verbosity (4=error,5=warning,6=info,7=verbose,8=debug,9=debug2)")
    oparser.add_option('-i', '--infile', action="store", dest="run.infile", default=False, metavar="PATH", help="Input file or directory")
    oparser.add_option('-o', '--out', action="store", dest="run.outfile", default=False, metavar="FILE", help="Output file")
    oparser.add_option('-t', '--tsukimi', action="store_true", dest="run.tsukimi", default=False, help="Tsukimi compat mode")

    # Mode selection options
    opg_mode = optparse.OptionGroup(oparser, "Mode Selection", "Choose operations mode for XBake (required). These options are mutually-exclusive.")
    opg_mode.add_option('--xcode', action="store_const", dest="run.mode", const="xcode", default=False, help="Transcode")
    opg_mode.add_option('--scan', action="store_const", dest="run.mode", const="scan", default=False, help="Scan for video")
    opg_mode.add_option('--ascan', action="store_const", dest="run.mode", const="ascan", default=False, help="Scan for audio/music")
    opg_mode.add_option('--ssonly', action="store_const", dest="run.mode", const="ssonly", default=False, help="Capture screenshot only")
    opg_mode.add_option('-d', '--server', action="store_const", dest="run.mode", const="srv", default=False, help="Run as a daemon (API server)")
    opg_mode.add_option('--set', action="store_const", dest="run.mode", const="set", default=False, help="Set overrides")

    # Scanning options
    opg_scan = optparse.OptionGroup(oparser, "Scanning", "Options for media scanner")
    opg_scan.add_option('-S', '--single', action="store_true", dest="run.single", default=False, help="Single-file Mode")
    opg_scan.add_option('-X', '--nosend', action="store_true", dest="scan.nosend", default=False, help="Disable sending data to remote server")
    opg_scan.add_option('--scraper', action="store", dest="scan.scraper", default=False, metavar="ID", help="Choose scraper to use (use 'help' to list available scrapers)")
    opg_scan.add_option('--procs', action="store", dest="scan.procs", default=False, metavar="PROCS", help="Number of processes to spawn (default is number of CPU threads)")
    opg_scan.add_option('--pretty', action="store_true", dest="scan.pretty", default=False, help="Pretty-print JSON output")
    opg_scan.add_option('-Z', '--nochecksum', action="store_true", dest="scan.nochecksum", default=False, help="Disable checksum calculation during file scanning")
    opg_scan.add_option('--nosave', action="store_false", dest="scan.savechecksum", default=False, help="Do not save checksum results in file extended attributes")
    opg_scan.add_option('--mforce', action="store_true", dest="scan.mforce", default=False, help="Force rescan all files, even if no changes detected")

    # Transcoding options
    opg_xcode = optparse.OptionGroup(oparser, "Transcoding", "Options for transcoding video")
    opg_xcode.add_option('--bake', action="store_true", dest="run.bake", default=False, metavar="SUBID", help="Bake subtitles (hardsub)")
    opg_xcode.add_option('--subid', action="store", dest="xcode.subid", default=False, metavar="SUBID", help="Subtitle track ID (default=auto, track marked 'default')")
    opg_xcode.add_option('--subtype', action="store", dest="xcode.subtype", default=False, metavar="TYPE", help="Specify subtitle track type [ass,srt] (default=ass)")
    opg_xcode.add_option('--scale', action="store", dest="xcode.scale", default=False, metavar="RES", help="Scale video resolution (RES=width:height)")
    opg_xcode.add_option('--crf', action="store", dest="xcode.crf", default=False, metavar="CRF", help="x264 CRF: lower is better quality, but higher bitrate (default=20)")
    opg_xcode.add_option('--x264preset', action="store", dest="xcode.libx264_preset", default=False, metavar="NAME", help="x264 preset; must be a valid libx264 preset (default=medium)")
    opg_xcode.add_option('--anamorphic', action="store_true", dest="xcode.anamorphic", default=False, help="Perform anamorphic widescreen compensation")
    opg_xcode.add_option('--aid', action="store", dest="xcode.aid", default=False, metavar="AID", help="Audio track ID (default=auto, track marked 'default')")
    opg_xcode.add_option('--abr', action="store", dest="xcode.abr", default=False, metavar="KBPS", help="Audio bitrate in kbps (default=128)")
    opg_xcode.add_option('--acopy', action="store_true", dest="xcode.acopy", default=False, help="Audio track, direct stream copy (default if stream is AAC Stereo)")
    opg_xcode.add_option('--downmix', action="store_true", dest="xcode.downmix", default=False, help="Downmix audio from 5.1 to Stereo")
    opg_xcode.add_option('--flv', action="store_true", dest="xcode.flv", default=False, help="Output in FLV container")
    opg_xcode.add_option('--daignore', action="store_true", dest="xcode.daignore", default=False, help="Ignore errors when dumping attachments")
    opg_xcode.add_option('-x', '--noupdate', action="store_true", dest="run.noupdate", default=False, help="Do not commit updates to database")

    # Framegrab options
    opg_vscap = optparse.OptionGroup(oparser, "Framegrab", "Options for screenshot capture")
    opg_vscap.add_option('--vscap', action="store", dest="run.vscap", default=False, metavar="OFFSET", help="Capture frame at specified OFFSET in seconds (integer)")
    opg_vscap.add_option('--nothumbs', action="store_true", dest="vscap.nothumbs", default=False, help="Capture and store original image only; do not generate thumbnails or WebP versions")

    # Versioning options
    opg_version = optparse.OptionGroup(oparser, "ID & Version Info", "Options for file ID and encode versioning")
    opg_version.add_option('--id', action="store", dest="run.id", default=False, metavar="ID", help="Specify file ID; metadata is pulled from database")
    opg_version.add_option('-A', '--autoid', action="store_true", dest="vid.autoid", default=False, help="Calculate ID from MD5 checksum (use for existing entries)")
    opg_version.add_option('-H', '--location', action="store", dest="vid.location", default=False, metavar="HOSTKEY", help="Specify source location key (hostname with underscores)")
    opg_version.add_option('--vername', action="store", dest="vid.vername", default=False, metavar="NAME", help="Specify version name")

    # Metadata options
    opg_meta = optparse.OptionGroup(oparser, "Metadata & Overrides", "Options for specifying additional metadata which will be included in the database entry for this video. Also used for setting overrides with --set mode.")
    opg_meta.add_option('--title', action="store", dest="run.title", default=False, metavar="VAL", help="Metadata: Episode/Video Title")
    opg_meta.add_option('--dub', action="store", dest="run.dub", default=False, metavar="LANG", help="Metadata: Dub Language")
    opg_meta.add_option('--special', action="store", dest="run.special", default=False, metavar="VAL", help="Metadata: Special Episode Title")
    opg_meta.add_option('--series', action="store", dest="run.series", default=False, metavar="VAL", help="Series Title")
    opg_meta.add_option('--episode', action="store", dest="run.episode", default=False, metavar="NUM", help="Episode Number")
    opg_meta.add_option('--season', action="store", dest="run.season", default=False, metavar="NUM", help="Season Number")
    opg_meta.add_option('--fansub', action="store", dest="run.fansub", default=False, metavar="GROUP", help="Fansub Group Name")
    opg_meta.add_option('--tvdb', action="store", dest="run.tvdb_id", default=False, metavar="ID", help="TheTVDb ID")
    opg_meta.add_option('--mal', action="store", dest="run.mal_id", default=False, metavar="ID", help="MyAnimeList ID")
    opg_meta.add_option('--tdex', action="store", dest="run.tdex_id", default=False, metavar="ID", help="Overrides: tdex_id")
    opg_meta.add_option('--ignore', action="store_true", dest="run.ignore", default=False, help="Overrides: Set 'ignore' flag")
    opg_meta.add_option('--clear', action="store_true", dest="run.ovr_clear", default=False, help="Overrides: Clear all overrides")

    # Daemon/Server options
    opg_srv = optparse.OptionGroup(oparser, "Daemon", "Options that apply when XBake is running as a daemon (server mode)")
    opg_srv.add_option('--pidfile', action="store", dest="srv.pidfile", default=False, metavar="PATH", help="PID file [default: xbake.pid]")
    opg_srv.add_option('--iface', action="store", dest="srv.iface", default=False, metavar="IP", help="Interface to bind to [default: 0.0.0.0]")
    opg_srv.add_option('--port', action="store", dest="srv.port", default=False, metavar="PORT", help="Port to listen on [default: 7037]")
    opg_srv.add_option('--nofork', action="store_true", dest="srv.nofork", default=False, help="Don't fork (stay loaded in the foreground)")
    opg_srv.add_option('--debug', action="store_true", dest="srv.debug", default=False, help="Enable debug mode (Flask)")

    # add groups to parser
    oparser.add_option_group(opg_mode)
    oparser.add_option_group(opg_scan)
    oparser.add_option_group(opg_xcode)
    oparser.add_option_group(opg_vscap)
    oparser.add_option_group(opg_version)
    oparser.add_option_group(opg_meta)
    oparser.add_option_group(opg_srv)

    options, args = oparser.parse_args(sys.argv[1:])
    vout = vars(options)

    if len(args) >= 1:
        vout['run.infile'] = args[0]
    if len(args) >= 2:
        vout['run.outfile'] = args[1]

    if vout['run.verbose']:
        vout['run.verbose'] += 6
        vout['core.loglevel'] = vout['run.verbose']
    if vout['run.verbose'] or vout['core.loglevel']:
        loglevel(int(vout['core.loglevel']))
    if vout['run.quiet']:
        vout['core.loglevel'] = LL.ERROR
        loglevel(int(vout['core.loglevel']))

    return vout

##############################################################################
## Entry point
##
def _main():
    """CLI entry point"""
    # Show banner
    if len(sys.argv) < 2 or sys.argv[1] == '-h' or sys.argv[1] == '--help':
        show_banner()

    # Set default loglevel
    loglevel(defaults['core']['loglevel'])

    # parse CLI options and load running config
    xopt = parse_cli()
    config = rcfile.loadConfig(cliopts=xopt)
    configure_logging(config)

    # Get ffmpeg version
    ffmpeg.locateAll(config)
    ffver = ffmpeg.version()
    logthis("FFmpeg Version:", suffix="%s (%s)" % (ffver['version'], ffver['date']), loglevel=LL.VERBOSE)
    tstatus('version', xbake_version=__version__, xbake_date=__date__, ffmpeg=ffver, path=os.environ['PATH'])

    # Ready
    logthis("Configuration done. config =", suffix=str(config), loglevel=LL.DEBUG)

    # Set quiet exception handler for non-verbose operation
    if config.core['loglevel'] < LL.VERBOSE:
        sys.excepthook = exceptionHandler

    # Set default return code to 1
    rcode = 1
    if config.scan['scraper'] == "help":
        scrapers.loadModules()
        modlist = scrapers.getModuleList()
        print("** Available scraper modules:\n")
        for tm in modlist:
            print("{tm[name]:16} {tm[desc]} [{tm[author]}] (v{tm[version]} {tm[date]})".format(tm=tm))
        print("")
        rcode = 250
    elif config.run['mode'] == "xcode":
        rcode = xcode.run(config)
    elif config.run['mode'] == "ssonly":
        rcode = ssonly.run(config)
    elif config.run['mode'] == "scan":
        rcode = mscan.run(config)
    elif config.run['mode'] == "ascan":
        rcode = ascan.run(config)
    elif config.run['mode'] == "srv":
        daemon.start(config)
    elif config.run['mode'] == "set":
        if config.run['ovr_clear'] is True:
            rcode = mscan.unsetter(config)
        else:
            rcode = mscan.setter(config)
    else:
        oparser.print_help()
        rcode = 250

    sys.exit(rcode)

if __name__ == '__main__':
    _main()
