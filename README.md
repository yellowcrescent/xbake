# yc_xbake
*yc_xbake* is a multi-purpose tool for cataloging and transcoding video files. It was originally written in PHP to bake subtitles and transcode video for [ycplay.tv](https://ycplay.tv/), but is in the process of being ported to Python.

> Copyright (c) 2013-2015 J. Hipps / Neo-Retro Group

## Installing Prerequisite packages
Below are instructions for installation on Debain or Debian-based derivatives, such as Ubuntu. The package names will be the same or similar for other platforms, so adapt as necessary.

#### Python PIP and Development Libraries
If you haven't done so already, be sure you have a copy of the Python dev package, as well as `pip`.

    sudo apt-get install python-dev python-pip

#### PyMongo
    sudo pip install pymongo

#### Redis
    sudo pip install redis

## Installing yc_xbake
Installation is currently done by cloning the repository from BitButcket, then creating a symlink to `/usr/local/bin` so that it remains in your path for easy execution.

    git clone https://bitbucket.org/yellowcrescent/yc_xbake
    cd yc_xbake
    sudo ln -s $PWD/yc_xbake /usr/local/bin/yc_xbake

## Installing Server Software

### Redis
Redis is really easy to install and works right out of the box. This will install the Redis server and `redis-cli` program, which is handy to manually issue commands to Redis, as well as using its *monitor* mode to view commands in realtime from client applications.

    sudo apt-get install redis-server redis-cli

### MongoDB
MongoDB can be installed via `apt-get` easily. However, the packages in aptitude are typically not current. Please read the instructions on the MongoDB page. Below is a summary on installation of MongoDB 3.x on Debian or Ubuntu

- MongoDB installation on Ubuntu: http://docs.mongodb.org/master/tutorial/install-mongodb-on-ubuntu/
- MongoDB installation on Debian: http://docs.mongodb.org/master/tutorial/install-mongodb-on-debian/
- MongoDB downloads for other distros: https://www.mongodb.org/downloads

If you have added the *10gen*  apt repository as explained in the above instructions, you should be able to issue the following command to install MongoDB and requisite tools:

    sudo apt-get install mongodb-org-server mongodb-org-shell mongodb-org-tools

If you're using the packages from your distro's repository, use the following command:

    sudo apt-get install mongodb-server mongodb-shell mongodb-tools
