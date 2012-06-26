#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    any later version.

import os
import sys
import re
from DistUtilsExtra.auto import setup
from distutils.core import Extension


class replacement():
    """
    Reads file "infos.py" in that package and obtains from there the

    This "fake" class has been implemented because import priority between
    root and workingDir modules varies from Distro to Distro.
    """
    def __init__ (self, path ):
        self.__CapitalName__ = 'Calise'
        self.__LowerName__ = self.__CapitalName__.lower()
        with open( os.path.join(path, self.__LowerName__, 'infos.py') ) as fp:
            fc = fp.read().splitlines()
            for line in fc:
                if line[:11] == '__version__':
                    self.__version__ = (
                        '='.join(line.split('=')[1:]).replace(' ', '')[1:-1])


def get_svn_revision(path=None):
    """
    Returns the SVN revision in the form SVN-XXXX,
    where XXXX is the revision number.

    Returns SVN-unknown if anything goes wrong, such as an unexpected
    format of internal SVN files.
    """
    if path is None:
        #path = os.path.dirname(os.path.realpath(__file__))
        baseName = sys.argv[0].replace("./","").\
            replace(os.path.basename(sys.argv[0]),"")
        path = os.path.join(os.getcwd(), baseName)
    infos = replacement(path)
    rev = None
    db_path = '%s/.svn/wc.db' % path

    try:
        with open(db_path) as fp:
            content = fp.read().replace("svn/ver/","\nsvn/ver/").split("\n")
        prog = re.compile('svn/ver/([0-9]+)/')
        revisions = []
        for line in content:
            z = prog.match(line)
            if z is not None:
                revisions.append(int(z.group(1)))
        rev = max(revisions)
    except IOError:
        pass
    if rev:
        versionString = u'SVN-%s' % rev
        with open(os.path.join(path, infos.__LowerName__, 'infos.py')) as fp:
            fc = fp.read()
            fc = fc.replace(
                '__version__ = \'%s\'' % infos.__version__,
                '__version__ = \'%s\'' % versionString, 1 )
        with open(os.path.join(path,infos.__LowerName__,'infos.py'),'w') as fp:
            fp.write(fc)
    else:
        versionString = infos.__version__
    return versionString


# instruct setup to build c modules with their included libraries
addModule1 = Extension("calise.screenBrightness",
    sources = ["src/modules/screenBrightness.c"],
    libraries = ["X11"])


setup(name = 'calise',
      version = get_svn_revision(),
      description = 'automatically adjust backlight trough a camera',
      author = "Nicolò Barbon",
      author_email = "smilzoboboz@gmail.com",
      url = 'http://sourceforge.net/projects/calise/',
      license = 'GNU GPL v3',
      ext_modules = [addModule1],
     )
