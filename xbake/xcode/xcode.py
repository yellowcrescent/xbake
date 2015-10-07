#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# xcode - xbake/xcode/xcode.py
# XBake: Transcoder
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_cpx
#
# Copyright (c) 2015 J. Hipps / Neo-Retro Group
#
# https://ycnrg.org/
#
###############################################################################

import sys
import os
import re
import json
import signal
import time
import subprocess

# Logging
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis

from xbake.xcode import ffmpeg

def transcode(infile,outfile=None,vername=None,id=None):
	pass
