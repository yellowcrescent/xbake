#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# scrapers - xbake/mscan/scrapers.py
# XBake: Scraper Functions
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
import json
import signal
import time
import subprocess
import requests
import xmltodict

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith
from xbake.common.logthis import print_r


def tvdb(xsea,tdex):
	"""
	TheTVDB.com (TVDB) Scraper
	"""
	conf = __main__.xsetup.config

	xstitle = tdex[xsea]['title']
	logthis("Retrieving series information from theTVDb for",suffix=xstitle,loglevel=LL.VERBOSE)

	tvdb_id = tdex[xsea].get('tvdb_id', tvdb_get_id(xstitle))

	if tvdb_id:
		if tdex[xsea].has_key('tvdb_id'):
			logthis("tvdb_id set from override",loglevel=LL.VERBOSE)
			del(tdex[xsea]['tvdb_id'])
		logthis("Got theTVDb Series ID#",suffix=tvdb_id,loglevel=LL.VERBOSE)

		# Retrieve entry from TVDB
		tvdb_info = tvdb_get_info(tvdb_id)
		tdex[xsea].update(tvdb_process(tvdb_info))
		logthis("theTVDb info:",suffix=tvdb_info,loglevel=LL.DEBUG2)
		return True
	else:
		logthis("No results in theTVDb found for series",suffix=xstitle,loglevel=LL.WARNING)
		return False


def tvdb_get_id(sername):
	"""
	TVDB: Get SeriesID from SeriesName
	"""
	conf = __main__.xsetup.config

	# Query TVDb for SeriesName
	xresp = getxml(conf['tvdb']['mirror'] + "/api/GetSeries.php", {'seriesname': sername})
	logthis("Got response from TVDb:",suffix=print_r(xresp),loglevel=LL.DEBUG2)

	snorm = normalize(sername)
	dres = xresp['answer'].get('Data',False)

	if dres:
		# Check if single or multiple results found
		xser = dres.get('Series')
		if isinstance(xser, list):
			logthis("Multiple results found",loglevel=LL.DEBUG)
			xsout = None
			for sk,sv in enumerate(xser):
				# Check against main SeriesName
				if normalize(sv.get('SeriesName','')) == snorm:
					logthis("Choosing exact match against SeriesName",loglevel=LL.DEBUG)
					xsout = sv
					break
				else:
					# Check against AliasNames
					xalias = sv.get('AliasNames','').split('|')
					for curali in xalias:
						if normalize(curali) == snorm:
							logthis("Choosing exact match against AliasNames",loglevel=LL.DEBUG)
							xsout = sv
							break
		else:
			logthis("Single match returned",loglevel=LL.DEBUG)
			xsout = xser

		if xsout:
			xid_out = xsout['seriesid']
			logthis("** SeriesID: %s / SeriesName: %s / AliasNames: %s" % (xsout.get('seriesid',''),xsout.get('SeriesName',''),xsout.get('AliasNames','')),loglevel=LL.VERBOSE)
		else:
			logthis("No exact match or alias match found. Choosing none.",prefix=sername,loglevel=LL.WARNING)
			xid_out = False
	else:
		logthis("Malformed or invalid response from theTVDb",loglevel=LL.ERROR)
		xid_out = False

	return xid_out


def tvdb_get_info(serid,slang="en"):
	"""
	TVDB: Retrieve series info
	"""
	conf = __main__.xsetup.config

	# Retrieve series data from TVDb
	xresp = getxml("%s/api/%s/series/%s/all/%s.xml" % (conf['tvdb']['mirror'],conf['tvdb']['apikey'],serid,slang))
	logthis("Got response from TVDb:",suffix=print_r(xresp),loglevel=LL.DEBUG2)

	if xresp['ok']:
		logthis("Retrieved series info OK",loglevel=LL.DEBUG)
		xdout = xresp['answer'].get('Data',False)
	else:
		logthis("Failed to retrieve series information from TVDb. return code =",suffix=xresp['status'],loglevel=LL.WARNING)
		xdout = False

	return xdout


def tvdb_process(indata):
	"""
	TVDB: Process data and enumerate artwork assets
	"""
	conf = __main__.xsetup.config
	imgbase = conf['tvdb']['imgbase']

	txc = {
			'tv': {}, 'xrefs': {}, 'synopsis': {}, 'xref': {},
			'artwork': {}, 'episodes': []
		  }

	iser = indata.get('Series',{})

	logthis("Processing info from theTVDb; enumerating artwork assets",loglevel=LL.VERBOSE)

	# Get list of genres; filter out any empty entries
	txc['genre'] = filter(lambda x: len(x.strip()), iser.get('Genre','').split('|'))

	# Get attributes
	txc['ctitle'] = iser.get('SeriesName',None)
	txc['xrefs']['tvdb'] = iser.get('id', None)
	txc['xrefs']['imdb'] = iser.get('IMDB_ID',None)
	txc['lastupdated'] = long(iser.get('lastupdated',time.time()))
	txc['tv']['network'] = iser.get('Network',None)
	txc['tv']['dayslot'] = iser.get('Airs_DayOfWeek',None)
	txc['tv']['timeslot'] = iser.get('Airs_Time',None)
	txc['tv']['debut'] = date2time(iser.get('FirstAired',None))
	txc['synopsis']['tvdb'] = iser.get('Overview',None)
	txc['status'] = iser.get('Status','unknown').lower()

	txc['fetched'] = long(time.time())

	# Get artwork defaults
	bandefs = {}
	bandefs['banners'] = iser.get('banner',None)
	bandefs['fanart'] = iser.get('fanart',None)
	bandefs['poster'] = iser.get('poster',None)

	# Get Artwork
	txc['artwork'] = tvdb_get_artwork(txc['xrefs']['tvdb'], bandefs)

	# Add Episode information
	txc['episodes'] = indata.get('Episode',[])

	logthis("Series metadata set.",loglevel=LL.VERBOSE)

	return txc

def tvdb_get_artwork(serid, adefs={}):
	"""
	TVDB: Fetch artwork data
	"""
	conf = __main__.xsetup.config
	imgbase = conf['tvdb']['imgbase']

	xdout = { 'banners': [], 'fanart': [], 'poster': [], 'season': [] }

	# Retrieve artwork data from TVDb
	logthis("Fetching artwork/banner data from theTVDb...",loglevel=LL.INFO)
	xresp = getxml("%s/api/%s/series/%s/banners.xml" % (conf['tvdb']['mirror'],conf['tvdb']['apikey'],serid))
	logthis("Got response from TVDb:",suffix=print_r(xresp),loglevel=LL.DEBUG2)

	if xresp['ok']:
		logthis("Retrieved banner info OK",loglevel=LL.DEBUG)
		blist = xresp['answer'].get('Banners',{}).get('Banner',[])

		for bb in blist:
			bantype = bb.get('BannerType','').lower().strip()
			tart = {
					'url': '%s/%s' % (imgbase,bb.get('BannerPath','')),
					'path': bb.get('BannerPath',''),
					'type2': bb.get('BannerType2',False),
					'tvdb_id': bb.get('id',False),
					'lang': bb.get('Language',None),
					'season': bb.get('Season','0'),
					'default': False,
					'selected': False
				   }
			if re.match('^(banner|fanart|poster|series|season)$', bantype):
				if bantype == 'series': bantype = 'banners'
				if bantype != 'season':
					if tart['path'] == adefs.get(bantype,False):
						tart['default'] = True
				xdout[bantype].append(tart)
			else:
				logthis("Unknown banner type encountered. bantype =",suffix=bantype,loglevel=LL.VERBOSE)

	else:
		logthis("Failed to retrieve series banner information from TVDb. return code =",suffix=xresp['status'],loglevel=LL.WARNING)
		xdout = {}

	logthis("Artwork check complete. Banners: %d / Fanart: %d / Poster: %d / Season: %d" % (len(xdout['banners']),len(xdout['fanart']),len(xdout['poster']),len(xdout['season'])),loglevel=LL.VERBOSE)

	return xdout

def mal(xsea,tdex):
	"""
	MyAnimeList.net (MAL) Scraper
	"""
	conf = __main__.xsetup.config


def getxml(uribase,qget=None,qauth=None):
	"""
	Make HTTP request and decode XML response
	"""
	useragent = "Mozilla/5.0 ("+os.uname()[0]+" "+os.uname()[4]+") XBake/"+__main__.xsetup.version+" (XBake Scraper - https://bitbucket.org/yellowcrescent/yc_xbake/)"
	rstat = { 'status': None, 'ok': False, 'answer': None }

	# Set headers
	rqheaders = { 'User-Agent': useragent }

	# Perform request
	logthis("Performing HTTP request to:",suffix=uribase,loglevel=LL.DEBUG)
	r = requests.get(uribase,params=qget,auth=qauth)

	# Process response
	logthis("Got response status:",suffix=str(r.status_code)+' '+r.reason,loglevel=LL.DEBUG)
	rstat['status'] = r.status_code

	# If all went well, decode the XML response
	if r.status_code == 200:
		rstat['answer'] = xmltodict.parse(r.text)
		rstat['ok'] = True

	return rstat


def normalize(xname):
	"""
	Normalize input string for use as a tdex_id
	"""
	nrgx = u'[\'`\-\?!%&\*@\(\)#:,\.\/\\;\+=\[\]\{\}\$\<\>]'
	urgx = u'[ ★☆]'
	return re.sub(urgx,'_',re.sub(nrgx,'', xname)).lower().strip()


def date2time(dstr,fstr="%Y-%m-%d"):
	"""
	Convert date string to integer UNIX epoch time
	"""
	try:
		return long(time.mktime(time.strptime(dstr,fstr)))
	except e:
		logthis("strptime() conversion failed:",suffix=e,loglevel=LL.VERBOSE)
		return None
