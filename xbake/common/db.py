#!/usr/bin/env python
# coding=utf-8
###############################################################################
#
# db - xbake/common/db.py
# XBake: Database Interface
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
import pymongo
import redis

# Logging & Error handling
from xbake.common.logthis import C
from xbake.common.logthis import LL
from xbake.common.logthis import logthis
from xbake.common.logthis import ER
from xbake.common.logthis import failwith


class mongo:
    """Hotamod class for handling Mongo stuffs"""
    xcon = None
    xcur = None
    conndata = {}
    silence = False

    def __init__(self, cdata={}, silence=False):
        """Initialize and connect to MongoDB"""
        self.silence = silence
        if cdata:
            self.conndata = cdata
        try:
            self.xcon = pymongo.MongoClient()
        except Exception as e:
            logthis("Failed connecting to Mongo --",loglevel=LL.ERROR,suffix=e)
            return False

        self.xcur = self.xcon[self.conndata['database']]
        if not self.silence: logthis("Connected to Mongo OK",loglevel=LL.INFO,ccode=C.GRN)

    def find(self, collection, query):
        xresult = {}
        xri = 0
        for tresult in self.xcur[collection].find(query):
            xresult[xri] = tresult
            xri += 1
        return xresult

    def update_set(self, collection, monid, setter):
        try:
            self.xcur[collection].update({'_id': monid}, {'$set': setter})
        except Exception as e:
            logthis("Failed to update document(s) in Mongo --",loglevel=LL.ERROR,suffix=e)

    def findOne(self, collection, query):
        return self.xcur[collection].find_one(query)

    def insert(self, collection, indata):
        return self.xcur[collection].insert_one(indata).inserted_id

    def insert_many(self, collection, indata):
        return self.xcur[collection].insert_many(indata).inserted_ids

    def count(self, collection):
        return self.xcur[collection].count()

    def getone(self, collection, start=0):
        for trez in self.xcur[collection].find().skip(start).limit(1):
            return trez

    def close(self):
        if self.xcon:
            self.xcon.close()
            if not self.silence: logthis("Disconnected from Mongo")

    def __del__(self):
        """Disconnect from MongoDB"""
        if self.xcon:
            self.xcon.close()
            #if not self.silence: logthis("Disconnected from Mongo")

class redis:
    """Hotamod class for Redis stuffs"""
    rcon = None
    rpipe = None
    conndata = {}
    rprefix = 'hota'
    silence = False

    def __init__(self, cdata={}, prefix='',silence=False):
        """Initialize Redis"""
        self.silence = silence
        if cdata:
            self.conndata = cdata
        if prefix:
            self.rprefix = prefix
        try:
            self.rcon = xredis.Redis(**self.conndata)
        except Exception as e:
            logthis("Error connecting to Redis",loglevel=LL.ERROR,suffix=e)
            return

        if not self.silence: logthis("Connected to Redis OK",loglevel=LL.INFO,ccode=C.GRN)


    def set(self, xkey, xval, usepipe=False, noprefix=False):
        if noprefix: zkey = xkey
        else:        zkey = '%s:%s' % (self.rprefix, xkey)
        if usepipe:
            xrez = self.rpipe.set(zkey, xval)
        else:
            xrez = self.rcon.set(zkey, xval)
        return xrez

    def get(self, xkey, usepipe=False, noprefix=False):
        if noprefix: zkey = xkey
        else:        zkey = '%s:%s' % (self.rprefix, xkey)
        if usepipe:
            xrez = self.rpipe.set(zkey)
        else:
            xrez = self.rcon.get(zkey)
        return xrez

    def incr(self, xkey, usepipe=False):
        if usepipe:
            xrez = self.rpipe.incr('%s:%s' % (self.rprefix, xkey))
        else:
            xrez = self.rcon.incr('%s:%s' % (self.rprefix, xkey))
        return xrez

    def exists(self, xkey, noprefix=False):
        return self.rcon.exists('%s:%s' % (self.rprefix, xkey))

    def keys(self, xkey, noprefix=False):
        if noprefix: zkey = xkey
        else:        zkey = '%s:%s' % (self.rprefix, xkey)
        return self.rcon.keys(zkey)

    def makepipe(self):
        try:
            self.rpipe = self.rcon.pipeline()
        except Exception as e:
            logthis("Error creating Redis pipeline",loglevel=LL.ERROR,suffix=e)

    def execpipe(self):
        if self.rpipe:
            self.rpipe.execute()
            logthis("Redis: No pipeline to execute",loglevel=LL.ERROR)

    def count(self):
        return self.rcon.dbsize()

    def __del__(self):
        pass
        #if not self.silence: logthis("Disconnected from Redis")

