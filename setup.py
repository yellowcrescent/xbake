#!/usr/bin/env python
# coding=utf-8

from setuptools import setup, find_packages
setup(
    name = "yc_xbake",
    version = "0.10.172",
    author = "Jacob Hipps",
    author_email = "jacob@ycnrg.org",
    license = "MIT",
    description = "Tool for cataloging and transcoding video files",
    keywords = "video scraper scanner catalog subtitles",
    url = "https://bitbucket.org/yellowcrescent/yc_xbake/",

    packages = find_packages(),
    scripts = ['yc_xbake'],

    install_requires = ['docutils>=0.3','setproctitle','pymongo>=3.0','redis>=2.10','pymediainfo>=1.4.0','enzyme>=0.4.1','distance>=0.1.3','requests>=2.2.1','xmltodict>=0.9.2','xattr>=0.7.8','flask>=0.10.1','lxml>=3.5.0'],

    package_data = {
        '': [ '*.md' ],
    }

    # could also include long_description, download_url, classifiers, etc.
)
