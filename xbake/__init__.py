#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake
YC XBake
Media cataloguing, renaming, sub baking and transcoding utility

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2017 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

Refer to README.md for installation and usage instructions.

"""

from xbake.common.logthis import LL

__version__ = "0.10.191"
__date__ = "03 Jul 2017"

defaults = {
                'run': {
                    'mode': None,
                    'infile': None,
                    'outfile': None,
                    'id': None,
                    'bake': False,
                    'vscap': None,
                    'single': False,
                    'tsukimi': False,
                    'ovr_clear': False,
                    'noupdate': False
                },
                'core': {
                    'loglevel': LL.INFO
                },
                'vid': {
                    'autoid': 1,
                    'location': None,
                    'vername': None
                },
                'vscap': {
                    'basedir': ".",
                    'webp_m': 6,
                    'webp_q': 90,
                    'nothumbs': False
                },
                'mongo': {
                    'uri': "mongodb://localhost:27017/ycplay"
                },
                'redis': {
                    'host': "localhost",
                    'port': 6379,
                    'db': 6,
                    'prefix': "xbake"
                },
                'xcode': {
                    'subtype': "ass",
                    'subid': "auto",
                    'abr': 128,
                    'downmix': 'auto',
                    'acopy': 'auto',
                    'aid': None,
                    'srt_style': "FontName=MyriadPro-Semibold,Outline=1,Shadow=1,FontSize=24",
                    'fontdir': "~/.fonts",
                    'fontsave': False,
                    'scale': None,
                    'flv': False,
                    'anamorphic': False,
                    'crf': 20,
                    'libx264_preset': "medium",
                    'show_ffmpeg': True
                },
                'scan': {
                    'scraper': "tvdb",
                    'mforce': False,
                    'nochecksum': False,
                    'savechecksum': True,
                    'output': None,
                    'follow_symlinks': True,
                    'workaround_mediainfo_bugs': True,
                    'tempdir': "/tmp",
                    'procs': 0
                },
                'tvdb': {
                    'mirror': "http://thetvdb.com",
                    'imgbase': "http://thetvdb.com/banners",
                    'apikey': None
                },
                'mal': {
                    'user': None,
                    'password': None
                },
                'ffmpeg': {
                    'path': None
                },
                'srv': {
                    'pidfile': "xbake.pid",
                    'iface': "0.0.0.0",
                    'port': 7037,
                    'nofork': False,
                    'debug': False,
                    'shared_key': '',
                    'xfer_path': '.',
                    'xfer_hostonly': False,
                    'xcode_outpath': '.',
                    'xcode_default_profile': None,
                    'xcode_scale_allowance': 10,
                    'xcode_show_ffmpeg': False
                }
            }
