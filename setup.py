#!/usr/bin/env python
# coding=utf-8
# pylint: disable=W,C

from setuptools import setup, find_packages
setup(
    name = "yc_xbake",
    version = "0.10.190",
    author = "Jacob Hipps",
    author_email = "jacob@ycnrg.org",
    license = "MIT",
    description = "Tool for cataloging and transcoding video files",
    keywords = "video scraper scanner catalog subtitles transcode encode convert metadata",
    url = "https://git.ycnrg.org/projects/YXB/repos/yc_xbake",

    packages = find_packages(),
    scripts = [],

    install_requires = ['docutils', 'setproctitle', 'pymongo', 'redis', 'pymediainfo', 'enzyme',
                        'distance', 'requests', 'xmltodict', 'xattr', 'flask>=0.10.1', 'lxml',
                        'mutagen', 'arrow>=0.7.0'],

    package_data = {
        '': [ '*.md' ],
    },

    entry_points = {
        'console_scripts': [ 'xbake = xbake.cli:_main' ]
    }

    # could also include long_description, download_url, classifiers, etc.
)
