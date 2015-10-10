#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# util - xbake/mscan/util.py
# XBake: Scanner Utility Functions
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_cpx
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
import json
import signal
import time
import subprocess

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith

rhpath = '/usr/bin/rhash'

def md5sum(fname):
	return rhash(fname, "md5")['md5']

def rhash(infile,hlist):
	global rhpath
	if type(hlist) == str:
		hxlist = [ hlist ]
	hxpf = ""
	for i in hxlist:
		hxpf += "%%{%s} " % i
	rout = subprocess.check_output([rhpath,'--printf',hxpf,infile])
	rolist = rout.split(' ')
	hout = {}
	k = 0
	for i in rolist:
		try:
			hout[hxlist[k]] = i
		except IndexError:
			break
		k += 1
	return hout
