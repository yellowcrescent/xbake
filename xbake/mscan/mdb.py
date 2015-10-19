#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# mdb - xbake/mscan/mdb.py
# XBake: Meta DB
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

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith

class MCMP:
	NOMATCH = 0
	RENAMED = 1
	NOCHG   = 2

# RCData store
rcdata = {}
# TDex store
tdex = {}

def mkey_match(mkid,mkreal):
	"""
	Check against MDB for matches
	"""
	dxm = rcdata.get(mkid,False)
	if dxm is False:
		return MCMP.NOMATCH
	elif unicode(dxm) == unicode(mkreal):
		return MCMP.NOCHG
	else:
		return MCMP.RENAMED


def series_add(sname,ovrx=False):
	"""
	Add series to tdex
	"""
	snamex = normalize(sname)

	if tdex.has_key(snamex):
		logthis("inc count for series:",suffix=snamex,loglevel=LL.DEBUG)
		tdex[snamex]['count'] += 1
	else:
		logthis("New series found:",suffix=snamex,loglevel=LL.DEBUG)
		tdex[snamex] = { 'title': sname, 'count': 1 }
		if ovrx:
			if ovrx.has_key('tvdb_id'): tdex[snamex]['tvdb_id'] = ovrx['tvdb_id']
			if ovrx.has_key('mal_id'):  tdex[snamex]['mal_id'] = ovrx['mal_id']

	return snamex


def normalize(xname):
	"""
	Normalize input string for use as a tdex_id
	"""
	nrgx = u'[\'`\-\?!%&\*@\(\)#:,\.\/\\;\+=\[\]\{\}\$\<\>]'
	urgx = u'[ ★☆]'
	return re.sub(urgx,'_',re.sub(nrgx,'', xname)).lower().strip()