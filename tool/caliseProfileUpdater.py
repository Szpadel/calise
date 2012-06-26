#!/usr/bin/env python2
#
#    usage - caliseProfileUpdater.py profile1 [profile2] [...]
#    descr - convert calise 0.1.x profiles to 0.2.x (and saves them in the
#            same folder), keep in mind that original configuration files
#            won't be deleted
#
#    Copyright (C)   2012   Nicolo' Barbon
#
#    This file is part of Calise.
#
#    Calise is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    any later version.
#
#    Calise is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Calise.  If not, see <http://www.gnu.org/licenses/>.
#
#

import os
import sys
import ConfigParser


# options syntax:
#   Section: {Option: (oldSection, oldOption)}
options = {
    "Camera": {
        "offset": ("Brightness", "offset"),
        "delta": ("Brightness", "delta"),
        "camera": ("Camera", "camera"),
    },
    "Backlight": {
        "steps": ("Camera", "steps"),
        "offset": ("Camera", "bkofs"),
        "invert": ("Camera", "invert"),
        "path": ("Camera", "bfile"),
    },
    "Daemon": {
        "latitude": ("Positional", "latitude"),
        "longitude": ("Positional", "longitude"),
        "capnum": ("Camera", "capnum"),
        "capint": ("Camera", "capint"),
    },
    "Advanced": {
        "average": ("Other", "average"),
        "delay": ("Other", "delay"),
        "screen": ("Other", "screen"),
    },
}

oldSufx = ".cfg"
newSufx = ".conf"


def convert(oldConfigFile):
    if os.path.isfile(oldConfigFile):
        if oldConfigFile.endswith(oldSufx):
            newConfigFile = oldConfigFile[:-len(oldSufx)] + newSufx
        configOld = ConfigParser.RawConfigParser()
        configOld.read(oldConfigFile)
        configNew = ConfigParser.RawConfigParser()
        for section in options.keys():
            configNew.add_section(section)
            for key in options[section].keys():
                oldSec = options[section][key][0]
                oldKey = options[section][key][1]
                if configOld.has_option(oldSec, oldKey):
                    configNew.set(section, key, configOld.get(oldSec, oldKey))
        with open(newConfigFile, 'w') as ncf:
            configNew.write(ncf)
        return 0
    return 1


if len(sys.argv) > 1:
    for path in sys.argv[1:]:
        r = convert(path)
        print "%s processed with status %d" % (path, r)
else:
    sys.stderr.write(
        "You have to specify at least one input config file to be processed\n")
    sys.exit(1)