#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# fsutil - xbake/common/fsutil.py
# XBake: Filesystem utility functions
#
# @author   J. Hipps <jacob@ycnrg.org>
# @repo     https://bitbucket.org/yellowcrescent/yc_xbake
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
import xattr

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith


def xattr_get(xfile):
	"""
	Get extended file attributes
	Returns a dict with the 'user.' portion stripped from keys
	"""
	xout = {}
	try:
		for k,v in xattr.xattr(xfile).iteritems():
			xout[k.replace('user.','')] = v
	except e:
		logthis("Failed to get extended file attributes for",suffix=xfile,loglevel=LL.WARNING)
		logthis("xattr:",suffix=e,loglevel=LL.WARNING)

	return xout


def xattr_set(xfile,xsetter):
	"""
	Set extended file attributes
	Accepts a dict with attrib names that are not prefixed with the 'user.' namespace
	"""
	for k,v in xsetter.iteritems():
		try:
			xattr.setxattr(xfile, 'user.'+str(k), str(v))
		except e:
			logthis("Failed to set extended file attributes for",suffix=xfile,loglevel=LL.WARNING)
			logthis("xattr:",suffix=e,loglevel=LL.WARNING)
			return False

	return True
