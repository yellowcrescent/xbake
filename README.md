
![XBake icon](https://ycnrg.org/img/xbake_logo96.png)
# YC XBake
*yc_xbake* is a multi-purpose tool for cataloging and transcoding video files. It was originally written in PHP to bake subtitles and transcode video for [ycplay.tv](https://ycplay.tv/), but is in the process of being ported to Python.

> Copyright (c) 2013-2015 J. Hipps / Neo-Retro Group

## Installation
Below are instructions for installation on Debain or Debian-based derivatives, such as Ubuntu. The package names will be the same or similar for other platforms, so adapt as necessary.

#### Prerequisites: Python PIP and Development Libraries
If you haven't done so already, be sure you have a copy of the Python dev package, as well as `pip`.

    sudo apt-get install python-dev python-pip

#### Dependencies: Required Python modules
Required Python modules can be installed via PyPi/pip by using the command below:

    sudo pip install pymongo redis pymediainfo enzyme distance requests xmltodict xattr

#### Dependencies: Required Software
XBake also requires various pieces of software to perform its magic. This includes FFmpeg, ImageMagick, MkvToolNix, and MediaInfo. The command below will install everything *except* FFmpeg.

    sudo apt-get install imagemagick mkvtoolnix mediainfo

#### FFmpeg Installation
Proper installation of FFmpeg (with robust codec support) can be fairly complex. There are various pre-built packages (depending on your distribution), as well as many 3rd party repos that contain pre-built FFmpeg packages with the most-commonly used libraries/options enabled.

- [FFmpeg: Compilation Guide](https://trac.ffmpeg.org/wiki/CompilationGuide)
- [FFmpeg: ArchWiki](https://wiki.archlinux.org/index.php/FFmpeg)

#### Compiling FFmpeg (optional)
I have written a script that assists in compilation of FFmpeg and its dependency friends. It has been tested and works for CentOS 6 and 7, Ubuntu 14.04+, and Debian 7+. It will install necessary package dependencies, then download and compile other dependencies from source (such as libx264, libfaac, libass, etc.). Your mileage may vary-- basically,"type 'make' and pray". Below requires switching to root, as it installs various library dependencies. Before running the script, you may wish to read over it first-- the first few lines contain various options that allow enabling/disabling optional codecs, such as x265 (HEVC).

    sudo su -
    mkdir -p /opt/src
    cd /opt/src
    curl https://ycc.io/build/ffmpeg.sh > ffmpeg.sh
    chmod +x ffmpeg.sh
    ./ffmpeg.sh sysdeps


### Installing yc_xbake
After above dependencies have been met, installation can now be performed:

    git clone https://bitbucket.org/yellowcrescent/yc_xbake
    cd yc_xbake
    sudo python setup.py install

## Installing Server Software (optional)

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
