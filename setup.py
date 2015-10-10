#!/usr/bin/env python
# coding=utf-8

from setuptools import setup, find_packages
setup(
    name = "yc_xbake",
    version = "0.10.2",
    author = "Jacob Hipps",
    author_email = "jacob@ycnrg.org",
    license = "GPL",
    description = "Tool for cataloging and transcoding video files",
    keywords = "video scraper scanner catalog subtitles",
    url = "https://bitbucket.org/yellowcrescent/yc_xbake/",

    packages = find_packages(),
    scripts = ['yc_xbake'],

    install_requires = ['docutils>=0.3','pymongo>=3.0','redis>=2.10','mediainfo>=0.0.1','enzyme>=0.4.1'],

    package_data = {
        '': [ '*.md' ],
    }

    # could also include long_description, download_url, classifiers, etc.
)
