#    Copyright (C)   2011-2012   Nicolo' Barbon
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

import os
import sys
import logging
import tempfile
from xdg.BaseDirectory import save_config_path

from calise.infos import __LowerName__
from calise import optionsd as options


defaults = dict()


# Argument parse
def parseArguments(args):
    ap = options.coreGetArgs(args)
    ap.init_args()
    ap.parse_settings()
    

 # Set 'niceness' level to 10 if process has not been 'niced' by the user
def setNiceness(n=10):
    niceness = os.nice(0)
    if niceness == 0:
        niceness = os.nice(n)


def keepOnly(dkey='profile'):
    """ Leave only (profile) setting
    
    Leave only profile setting on settings global so that when
    options.profiler executes, it has no existing settings (which, due
    to function behaviour, won't overwrite.
    
    """
    for key in options.settings.keys():
        if key != dkey:
            del options.settings[key]


# Checks if specified loglevel exists
def checkLogLevelSyntax(string, defaultLogLevel):
    retCode = 0
    if not string.lower() in ['critical', 'error', 'warning', 'info', 'debug']:
        sys.stderr.write(
            "Invalid loglevel specified: %s, default (%s) will be used "
            "instead.\n" % (options.settings['loglevel'], defaultLogLevel))
        retCode = 1
    return retCode


# Checks if specified path's dir exists
def checkLogFileSyntax(string, defaultLogFile):
    retCode = 0
    if not os.path.isdir(os.path.dirname(string)):
        sys.stderr.write(
            "Directory %s does not exist, application log will be written to "
            "%s instead.\n" % (options.settings['logfile'], defaultLogFile))
        retCode = 1
    return retCode


def tempLoggerInit(prog):
    """ Temporary logger initialization
    
    To keep track of all log entries generated before profile is read (and
    'settings' var is in definitive state) a temporary logfile is created.
    
    NOTE: This function "pairs" with 'finalLoggerInit()' one
    
    """
    prog = os.path.basename(prog)
    if prog == 'calise.rewrite.py': prog = 'calise'  # NOTE: TEMPORARY!
    tempdir = tempfile.mkdtemp(prefix='%s-' % __LowerName__)
    logObject = tempfile.NamedTemporaryFile(
        prefix='%s-' % os.path.join(tempdir, __LowerName__), delete=False)
    global defaults
    defaults = options.getDefaultSettings(prog)
    logLevel = defaults['loglevel']
    logFile = logObject.name
    return logLevel, logFile


def finalLoggerInit(loggerClass, logLevel, logFile):
    for key in defaults.keys():
        if not options.settings.keys().count(key):
            options.settings[key] = defaults[key]
    if logLevel != options.settings['loglevel']:
        if (
            options.settings['loglevel'] is not None and
            checkLogLevelSyntax(options.settings['loglevel'], logLevel)
        ):
            options.settings['loglevel'] = logLevel
        loggerClass.changeLogLevel(options.settings['loglevel'])
    if logFile != options.settings['logfile']:
        if (
            options.settings['logfile'] is not None and
            checkLogFileSyntax(options.settings['logfile'], logFile)
        ):
            options.settings['logfile'] = logFile
        elif options.settings['logfile'] is not None:
            # copy temporary contents (pre-profile reading log) to the
            # new logfile specified in the profile just read
            with open(logFile, 'r') as fp:
                rp = fp.read()
            os.remove(logFile)
            with open(options.settings['logfile'], 'a') as fp:
                fp.write(rp)
        loggerClass.changeLogFile(options.settings['logfile'])


def loadProfile():
    pf = options.profiler()
    for cf in options.get_path(options.settings['profile']):
        pf.check_config(cf)


# Check for missing necessary settings
def checkMissingSettings(keys):
    retCode = 0
    if not (
        keys.count('offset') and keys.count('delta') and
        keys.count('steps') and keys.count('bkofs') and
        keys.count('invert') and keys.count('path') and
        keys.count('cam')):
            retCode = 1
    return retCode


def checkCalibrationNeed(suffix='.conf', default='default'):
    defName = default
    defConf = '%s%s' % (
        os.path.join(save_config_path(__LowerName__), defName), suffix)
    sysConf = '%s%s' % (
        os.path.join(os.path.join('/', 'etc', __LowerName__)), suffix)
    if not os.path.isfile(defConf) and not os.path.isfile(sysConf):
        options.settings['configure'] = True
    return options.settings['configure']


def getSettings():
    return options.settings

def setSetting(key, value):
    options.settings[key] = value
