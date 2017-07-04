
![XBake icon](https://ycnrg.org/img/xbake_logo96.png)
# YC XBake
*yc_xbake* is a multi-purpose tool for managing, cataloging, and transcoding video files, as well as baking subtitles (hardsubbing). It supports running as a daemon, and accepts scan information from authenticated local and remote hosts, and also manages transfer and encoding queues. Jobs can be submitted to the daemon via the HTTP API, or directly via Redis.

It was originally written in PHP to bake subtitles (hence the name) and transcode video for [ycplay.tv](https://ycplay.tv/), but has since been ported to Python and largely expanded.

## License
```
Copyright (c) 2013-2017 Jacob Hipps / Neo-Retro Group, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

# Table of Contents

- [Installation](#markdown-header-installation)
    - [Prerequisites](#markdown-header-prerequisites)
    - [Dependencies](#markdown-header-dependencies)
    - [Installing XBake](#markdown-header-installing-xbake)
    - [Additional Installation Information](#markdown-header-additional-installation-information)
        - [Installing Server Software](#markdown-header-installing-server-software)
        - [FFmpeg Installation](#markdown-header-ffmpeg-installation)
- [Usage Information](#markdown-header-usage-information)
    - [CLI Options](#markdown-header-cli-options)
    - [Examples](#markdown-header-examples)
    - [Configuration Files](#markdown-header-configuration-files)
    - [Overrides](#markdown-header-overrides)
- [Appendix & Specifications](#markdown-header-appendix)
    - [Option List](#markdown-header-option-list)
    - [MongoDB Schema](#markdown-header-mongodb-schema)
    - [API Reference](#markdown-header-api-reference)

## Installation
Below are instructions for installation on Debian and Debian-based distros (includes Ubuntu and Mint). The package names will be the same or similar for other platforms, so adapt as necessary.

#### Prerequisites
If you haven't done so already, be sure you have a copy of the Python dev package, as well as `pip`.

    sudo apt-get install python-dev python-pip

#### Dependencies
XBake also requires various pieces of software to perform its magic. This includes rhash, ImageMagick, MkvToolNix, MediaInfo, and WebP.
The command below also installs some dev libraries that may be required for compiling Python package dependencies.

    sudo apt-get install imagemagick mkvtoolnix mediainfo webp python-lxml librhash0 libffi-dev libxml2-dev libattr1-dev libtag1-dev

### Installing XBake
Once all of the system libraries have been installed, clone the git repository from Bitbucket (or Github), then run the
setuptools installer. This should also install all of the Python dependencies.

    git clone https://git.ycnrg.org/scm/yxb/yc_xbake.git
    cd yc_xbake
    sudo python setup.py install

If you plan to make changes to the code, or pull updates frequently, you may want to use the 'develop' command,
rather than 'install'. This will create a stub to execute your progam, and links back to the source location.

    sudo python setup.py develop

You can now test to make sure everything has been installed properly by running:

    xbake

If all went well, you should see the help and usage output. If a program or dependency is missing, you should
receive an error message indicating what needs to be fixed. If ffmpeg is missing or not installed, you will
need to compile ffmpeg yourself (links below), or install it via a prebuilt package for your distro.

## Additional Installation Information

#### Dependencies: Python modules (Manual Installation)
Required Python modules can be installed via PyPi/pip by using the command below. These are typically installed
automatically by setuptools when using `python setup.py install`. If for some reason they are not installed
automatically, here is the list of required packages:

    sudo pip install pymongo redis pymediainfo enzyme distance requests xmltodict xattr flask lxml

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


## Installing Server Software

The following is supplemental information, and is only required if running XBake as a daemon.

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


# Usage Information

## CLI Options

### General Options
General-purpose options that can be used across most operations modes. With the exception of daemon/server mode, an input file is required for all other modes of operation.
```
  --version             show program's version number and exit
  -h, --help            show help message and exit
  -v, --verbose         Increase logging verbosity (-v Verbose, -vv Debug,
                        -vvv Debug2)
  -L NUM, --loglevel=NUM
                        Logging output verbosity
                        (4=error,5=warning,6=info,7=verbose,8=debug,9=debug2)
  -i PATH, --infile=PATH
                        Input file or directory
  -o FILE, --out=FILE   Output file
```

### Mode Selection
Choose operations mode for XBake (required). These options are mutually-exclusive.
```
    --xcode             Transcode
    --scan              Scan for & catalogue media
    --ssonly            Capture screenshot only
    -d, --server        Run as a daemon (API server)
```

### Scanning Options
Options for media scanner (modeset = `mscan`)
```
    -S, --single        Single-file Mode
    -X, --nosend        Disable sending data to remote server
    --scraper=ID        Choose scraper to use [tvdb,mal,ann] (default=tvdb)
    --pretty            Pretty-print JSON output
    -Z, --nochecksum    Disable checksum calculation during file scanning
    --nosave            Do not save checksum results in file extended
                        attributes
    --mforce            Force rescan all files, even if no changes detected
```

### Transcoding Options
Options for transcoding video (modeset = `xcode`)
```
    --bake              Bake subtitles (hardsub)
    --subid=SUBID       Subtitle track ID (default=auto, track marked
                        'default')
    --subtype=TYPE      Specify subtitle track type [ass,srt] (default=ass)
    --scale=RES         Scale video resolution (RES=width:height)
    --crf=CRF           x264 CRF: lower is better quality, but higher bitrate
                        (default=20)
    --x264preset=NAME   x264 preset; must be a valid libx264 preset
                        (default=medium)
    --anamorphic        Perform anamorphic widescreen compensation
    --aid=AID           Audio track ID (default=auto, track marked 'default')
    --abr=KBPS          Audio bitrate in kbps (default=128)
    --acopy             Audio track, direct stream copy (default if stream is
                        AAC Stereo)
    --downmix           Downmix audio from 5.1 to Stereo
    --flv               Output in FLV container
    --daignore          Ignore errors when dumping attachments [deprecated]
```

### Framegrab Options
Options for screenshot capture
```
    --vscap=OFFSET      Capture frame at specified OFFSET in seconds (integer)
```

### ID & Version Options
Options for file identification and encode profile versioning
```
    -q ID, --id=ID      Specify file ID; metadata is pulled from database
    -A, --autoid        Calculate ID from MD5 checksum (use for existing
                        entries)
    -H HOSTKEY, --location=HOSTKEY
                        Specify source location key (hostname with
                        underscores)
    --vername=NAME      Specify version name
```
### Metadata Options
Options for specifying additional metadata to be included in the database entry for this video. If update mode is `MXM.NONE`, then these options will have absolutely no effect.
```
    --title=VAL         Metadata: Episode/Video Title
    --series=VAL        Metadata: Series Title
    --episode=NUM       Metadata: Episode Number
    --season=NUM        Metadata: Season Number
    --special=VAL       Metadata: Special Episode Title
    --fansub=GROUP      Metadata: Fansub Group Name
    --dub=LANG          Metadata: Dub Language
```
### Daemon Options
Options that apply when XBake is running as a daemon (modeset = `srv`)
```
    --pidfile=PATH      PID file [default: xbake.pid]
    --iface=IP          Interface to bind to [default: 0.0.0.0]
    --port=PORT         Port to listen on [default: 7037]
    --nofork            Don't fork (stay loaded in the foreground)
    --debug             Enable debug mode (Flask)
```


## Examples

##### Scanning a directory
This will scan the given directory for video files, extract information from the container and streams via mediainfo and mkvinfo, as well as caclulate various checksums using rhash (MD5, CRC32, ed2k). The file and directory names will be used to extrapolate the series title, which will be used for scraping series information from theTVDb, AniDB, etc.
```
yc_xbake --scan -i '/mnt/media/tvshows/Game of Thrones'
```
[Override files](#markdown-header-overrides) (`.xbake`) can be placed in directories to give XBake "hints" on a series title, season, TVDB ID, and a list of files to ignore. XBake can also read and store override information from extended file attributes, if supported by your filesystem.

Options specified in a user's [rcfile or local config file](#markdown-header-configuration-files) will always be taken into consideration (such as output type/location, scraper, and any other option).

##### Baking subtitles (hardsubbing)
When baking subtitles, XBake will check the list of tracks available in the source container, and choose the subtitle/text track marked as default. If there are multiple subtitle tracks, you can specify which you would like to use with the `--subid` option. When transcoding files with XBake, if no output file is specified, the same basename will be used, but the extension will be changed from `.mkv` to `.mp4` in the output filename.

```
yc_xbake --xcode --bake "Joukamachi no Dandelion - 01.mkv"
```
ASS subtitles and font attachments will be automatically extracted from the container for use during encoding. Note that it is important that the fonts are located in a directory that __fontconfig__ knows about. For this reason, XBake will by default move the extracted fonts to `~/.fonts`, since this path is commonly included in the list of places to check for fonts. You can adjust the include paths in `/etc/fonts/fonts.conf`, but __USE CAUTION__ as setting a stupid include path (like `/` or a path with a TON of files or subdirectory, like your home directory) can cause some major issues! If you actually use `~/.fonts` for your own personal fonts, you may want to choose a different directory with the `fontdir` option, or enable `fontsave`, which does not remove the font files after encoding is complete.

XBake works great for hardsubbing Advanced SubStation Alpha (ASS) subtitles, but can also do SubRip (SRT). Since SRT subs don't contain any style information, they tend to look pretty terrible when combined with whatever your machine considers the default sans-serif font. XBake uses Adobe's Myriad Pro Semibold when baking your SRT subs, but if you don't have that font, or have your own preference, you can adjust the `srt_style` option under the `[xcode]` section of your config file. Check the [option reference](#markdown-header-option-srt_style) for more info and full syntax.


### Configuration Files
All of the options that can be specified on the command line can also be defined in the config file (also called __rcfile__). The config file also allows setting many additional options that do not have corresponding CLI options.

When XBake first starts, it checks various locations for a configuration file. These locations are listed below:

- ~/.xbake
- ~/.xbake/xbake.conf
- ./xbake.conf
- /etc/xbake.conf

Options from these are merged together, then combined with the command-line options, with the CLI options taking precedence.

Each section of the config file contains a header, such as `[xcode]`. This header is important, so be sure to put the option lines under the correct header!

Example config snippet:
```
[mongo]
database = "xbake"

[tvdb]
apikey = "myAPIkey"

[xcode]
fontsave = 1

```
For a full list of available options, check out the [Option List](#markdown-header-option-list) section.

### Overrides
Overrides are settings that force a specific option while scanning for videos, or provide hints to the parser. To set overrides for a directory, you can create a JSON file named `.xbake` inside the directory.

Below is the contents of an example `.xbake` file for _Mirai Nikki_:

```
{
   "series_name": "Mirai Nikki",
   "tvdb_id": "249827",
   "mal_id": "10620",
   "season": 1,
   "ignore": [
      "bonus_video_01.mkv",
      "Bonus Video 02 (1920x1080 Hi10).mkv"
   ]
}
```

The above example shows all fields that can be set in an override file on a per-directory basis. Available overrides are shown below.

- __series_name__ (_user.media.seriesname_) - This series name will be entered into the database and used for any scraping (if the ID was unavailable, but it is being explicitly set here)
- __tvdb\_id__ (_user.media.xref.tvdb_) - theTVDb ID number; this skips searching for the series and retrieves the info directly. This is helpful for a series with an ambiguous name, or a series that has been rebooted
- __mal\_id__ (_user.media.xref.mal_) - MyAnimeList ID number; works just like tvdb_id
- __season__ (_user.media.season_) - explicitly sets the season number, rather than guessing via the directory or file naming structure
- __ignore__ - a list of files to ignore. Currently globs or regex is not supported, but I plan to implement support in the future. Note this must always be a list, even if there is only 1 file

Rather than creating an `.xbake` file, the overrides can also be set in the directory's extended attributes. The attribute name is given in the list above in parenthesis.

Files can also have individual overrides, but they can only be set via extended attributes. The supported options are the same as above, but also allows setting _episode number_ (__user.media.episode__) and _episode title_ (__user.media.title__).

Both files and directories support the __user.xbake.ignore__ flag, which is an extended attribute that can be set (no value is needed), which instructs XBake to skip that file (or entire directory if set on a directory). Note that the value of the attribute does not matter (it is a flag), so the attribute should be removed if the file/directory is to no longer be ignored.

More information on using extended file attributes and the XBake Xattrib Schema: https://onodera.ycnrg.org/xbake-schemas-xattrib/

## Appendix

### Option List

List of supported configuration options, followed by their default value.

##### core
- loglevel => 6

##### vid
- autoid => 1
- location => (not set)
- vername => (not set)

##### run
- vscap => (not set)
- infile => (not set)
- outfile => (not set)
- single => false
- mode => (not set)
- bake => false
- id => (not set)

##### mongo
- host => 'localhost'
- port => '27017'
- database => 'ycplay'

##### vscap
- webp_q => 90
- basedir => '.'
- webp_m => 6

##### scan
- mforce => false
- output => (not set)
- savechecksum => true
- scraper => 'tvdb'
- nochecksum => false

##### xcode
- libx264_preset => 'medium'
- fontsave => false
- acopy => 'auto'
- anamorphic => false
- scale => (not set)
- downmix => 'auto'
- srt_style => 'FontName=MyriadPro-Semibold,Outline=1,Shadow=1,FontSize=24'
- flv => false
- subid => 'auto'
- subtype => 'ass'
- abr => 128
- fontdir => (not set)
- crf => 20
- show_ffmpeg => true
- aid => (not set)

##### mal
- password => (not set)
- user => (not set)

##### ffmpeg
- path => false

##### tvdb
- imgbase => 'http://thetvdb.com/banners'
- apikey => false
- mirror => 'http://thetvdb.com'

##### redis
- host => 'localhost'
- prefix => 'xbake'
- db => 6
- port => 6379

##### srv
- pidfile => 'xbake.pid'
- xcode_scale_allowance => '10'
- xcode_show_ffmpeg => false
- xfer_path => '.'
- xfer_hostonly => false
- port => '7037'
- iface => '0.0.0.0'
- xcode_default_profile => (not set)
- nofork => false
- xcode_outpath => '.'
- shared_key => ''
- debug => false

### MongoDB Schemas

> See: https://onodera.ycnrg.org/yc_xbake-schema/

### API Reference

> TODO: This section

