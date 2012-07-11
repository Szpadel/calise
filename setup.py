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


# Reads file "infos.py" in that package and obtains from there the
#
# This "fake" class has been implemented because import priority between
# root and workingDir modules varies from Distro to Distro.
#
class replacement():
    def __init__ (self, path ):
        self.__CapitalName__ = 'Calise'
        self.__LowerName__ = self.__CapitalName__.lower()
        with open( os.path.join(path, self.__LowerName__, 'infos.py') ) as fp:
            fc = fp.read().splitlines()
            for line in fc:
                if line[:11] == '__version__':
                    self.__version__ = (
                        '='.join(line.split('=')[1:]).replace(' ', '')[1:-1])


# Obtain Setup Directory (even if called from outside)
def getsd():
    baseName = sys.argv[0].\
        replace('./', '').\
        replace(os.path.basename(sys.argv[0]), '')
    path = os.path.join(os.getcwd(), baseName)
    return path


# Developement versions track
#
# Returns either:
#  - SVN revision in the form SVN-XXXX, where XXXX is the revision number
#  - GIT shorthash in the form GIT-xxxxxxx, where xxxxxxx are first 7 chars of
#    sha1 hash
#
# Returns calise.infos.__version__ in no git nor svn exist
#
def get_svn_revision(path=None):
    if path is None:
        path = getsd()
    infos = replacement(path)
    # if there's git directory process as git
    if os.path.isdir(os.path.join(path, '.git')):
        gitRev = os.popen('git rev-parse --short HEAD')
        gitRev = gitRev.read()[:-1]
        versionString = u'GIT-%s' % gitRev
    # else if there's svn directory process as subversion
    elif os.path.isdir(os.path.join(path, '.svn')):
        db_path = os.path.join(path, '.svn', 'wc.db') % path
        with open(db_path) as fp:
            content = fp.read().replace('svn/ver/', '\nsvn/ver/').split('\n')
        prog = re.compile('svn/ver/([0-9]+)/')
        revisions = []
        for line in content:
            z = prog.match(line)
            if z is not None:
                revisions.append(int(z.group(1)))
        rev = max(revisions)
        versionString = u'SVN-%s' % rev
    else:
        versionString = None
    if versionString:
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


# remove '.py' suffix from scripts in 'bin' directory
def clearScriptExtensions(path=None):
    if path is None:
        path = getsd()
        binPath = os.path.join(path, 'bin')
    if os.path.isdir(binPath):
        retList = []
        for script in os.listdir(binPath):
            os.rename(
                os.path.join(binPath, script),
                os.path.join(binPath, script.replace('.py', '')))
            retList.append(os.path.join('bin', script.replace('.py', '')))


# restore '.py' suffix to scripts in 'bin' directory
def restoreScriptExtensions(path=None):
    if path is None:
        path = getsd()
        binPath = os.path.join(path, 'bin')
    if os.path.isdir(binPath):
        retList = []
        for script in os.listdir(binPath):
            os.rename(
                os.path.join(binPath, script),
                os.path.join(binPath, script + '.py'))
            retList.append(os.path.join('bin', script + '.py'))


clearScriptExtensions()
# instruct setup to build c modules with their included libraries
addModule1 = Extension(
    'calise.screenBrightness',
    sources = ['src/modules/screenBrightness.c'],
    libraries = ['X11'])
addModule2 = Extension(
    'calise.camera',
    sources = ['src/modules/camera.c'],)
# actual setup
setup(name='calise',
      version=get_svn_revision(),
      description="automatically adjust backlight trough a camera",
      author='Nicolò Barbon',
      author_email='smilzoboboz@gmail.com',
      url='http://calise.sourceforge.net/',
      license='GNU GPL v3',
      ext_modules=[addModule1, addModule2],
     )
restoreScriptExtensions()
