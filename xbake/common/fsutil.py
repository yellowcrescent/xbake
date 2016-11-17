#!/usr/bin/env python
# coding=utf-8
# vim: set ts=4 sw=4 expandtab syntax=python:
"""

xbake.common.fsutil
Filesystem utility functions

@author   Jacob Hipps <jacob@ycnrg.org>
@repo     https://git.ycnrg.org/projects/YXB/repos/yc_xbake

Copyright (c) 2013-2016 J. Hipps / Neo-Retro Group, Inc.
https://ycnrg.org/

"""

import sys
import os
import re
import json
import signal
import time
import xattr

# Logging & Error handling
from xbake.common.logthis import *


def xattr_get(xfile):
	"""
	Get extended file attributes
	Returns a dict with the 'user.' portion stripped from keys
	"""
	xout = {}
	try:
		for k, v in xattr.xattr(xfile).iteritems():
			xout[k.replace('user.', '')] = v
	except Exception as e:
		logthis("Failed to get extended file attributes for", suffix=xfile, loglevel=LL.WARNING)
		logthis("xattr:", suffix=e, loglevel=LL.WARNING)

	return xout


def xattr_set(xfile, xsetter):
	"""
	Set extended file attributes
	Accepts a dict with attrib names that are not prefixed with the 'user.' namespace
	"""
	for k, v in xsetter.iteritems():
		try:
			xattr.setxattr(xfile, 'user.'+str(k), str(v))
		except Exception as e:
			logthis("Failed to set extended file attributes for", suffix=xfile, loglevel=LL.WARNING)
			logthis("xattr:", suffix=e, loglevel=LL.WARNING)
			return False

	return True


def xattr_del(xfile, xsetter):
	"""
	Remove extended file attributes
	Accepts a list/array with attrib names that are not prefixed with the 'user.' namespace
	"""
	for k in xsetter:
		try:
			xattr.removexattr(xfile, 'user.'+str(k))
		except Exception as e:
			logthis("Failed to remove extended file attributes for", suffix=xfile, loglevel=LL.WARNING)
			logthis("xattr:", suffix=e, loglevel=LL.WARNING)
			return False

	return True
