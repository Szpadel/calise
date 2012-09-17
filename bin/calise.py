#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
#    Calise - CameraLightSensorProject
#             calculates ambient brightness and suggests (or sets)
#             screen's correct backlight level using a camera.
#
#    Copyright (C)   2011-2012   Nicolo' Barbon
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

import gettext
import locale
import os
import sys
import logging
import signal
import time
from subprocess import Popen, PIPE  # NOTE: probably temporary

from calise.infos import __LowerName__
from calise import optionsd as options
from calise.shared import *


try:
    locale.setlocale(locale.LC_ALL, '')
    gettext.bindtextdomain( __LowerName__)
    gettext.textdomain(__LowerName__)
    gettext.install(__LowerName__, unicode=False)
except locale.Error, err:
    sys.stderr.write(err)


# manage clean exit/pause
def clear(sig=None, func=None):
    if sig == signal.SIGTERM or sig == signal.SIGINT:
        if trd is not None:
            trd.func.sig = 'quit'
            for x in range(20):
                if not trd.isAlive(): break
                time.sleep(0.1)
                if x == 19:
                    os.kill(os.getpid(), signal.SIGKILL)
        sys.exit(sig)
    elif sig == signal.SIGTSTP:
        if trd is not None:
            trd.func.sig = 'pause'
    elif sig == signal.SIGCONT:
        if trd is not None:
            trd.func.sig = 'resume'


def printBriefInfos():
    print((
        _("Using \"%s\" profile") + "\n" +
        _("Camera") + ": %s\n" +
        _("Sysfs backlight path") + ": %s\n" +
        _("Backlight steps") + ": %s\n" +
        _("Delta and offset") + ": %.3f, %.1f\n" +
        _("Time gap") + ": %.2f (%.2f/s)\n" +
        _("Number of values to average") + ": %d (%d sec)") % (
        options.settings['profile'],
        options.settings['cam'],
        options.settings['path']\
            [:-len('/' + os.path.basename(options.settings['path']))],
        ' -> '.join([
            str(options.settings['bkofs']),
            str(options.settings['bkofs'] + options.settings['steps'])]),
        options.settings['delta'], options.settings['offset'],
        options.settings['gap'], 1.0 / options.settings['gap'],
        options.settings['avg'],
        options.settings['avg'] * options.settings['gap'],)
    )


def cliInterface():
    ''' Interactive cli interface
    
    Interactive interface commands:
        q) exit
        p) pause/resume
        a) start/stop collecting data
        e) export collected data
    
    '''
    from calise.getkey import _Getch
    getch = _Getch()
    while trd.isAlive():
        try:
            ch = getch()
        except IOError as err:
            if err.errno == 4:
                ch = '0'
        if ch in 'qQ':
            trd.func.sig = 'quit'
            for x in range(20):
                if not trd.isAlive():
                    break
                time.sleep(0.1)
                if x == 19:
                    os.kill(os.getpid(), signal.SIGKILL)
            break
        if ch in 'eE':
            trd.func.sig = 'export'
        if ch in ' pP':
            if trd.func.sig is not 'pause':
                trd.func.sig = 'pause'
            else:
                trd.func.sig = 'resume'
        if ch in 'aA':
            current = options.settings['record']
            options.settings['record'] = not current
            trd.func.arguments['record'] = not current
    print ''


def isServiceAlive():
    ''' temporary fix until proper implementation
    Checks for a running service instance and if so, stops it (at the end of
    execution service will be started again, take a look at the end of this
    page

    NOTE: This implementation is extremely experimental and temporary, real
          implementation needs return codes from dbus objects (can be done
          with tuple)
    '''
    service_wasAlive = False
    pcs = Popen(['calised', '--check'], stdout=PIPE, stderr=PIPE)
    dmp = pcs.communicate()
    # service alive and running
    if ''.join(dmp[0].split('\n')) == "service is alive and running":
        return True
    # service alive and paused
    elif ''.join(dmp[0].split('\n')) == "service is alive but paused":
        return False
    # service is not alive
    elif ''.join(dmp[0].split('\n')) == "service is not alive":
        return False
    # warning: unable to check service execution
    elif ''.join(dmp[0].split('\n')).startswith("warning: "):
        return None

def pauseService(action='pause'):
    pcs = Popen(['calised', '--%s' % action], stdout=PIPE, stderr=PIPE)
    dmp = pcs.communicate()
    if ''.join(dmp[0].split('\n')).startswith("warning: "):
        logger.warning("Unable to %s a running calised execution" % action)
        return False
    else:
        return True



def main():
    parseArguments(sys.argv[1:])
    setNiceness(10)
    keepOnly('profile')
    logLevel, logFile = tempLoggerInit(sys.argv[0])
    tempdir = os.path.dirname(logFile)
    #setSetting('logfile', logObject.name)            # NOTE: service-only
    lg = options.wlogger(logLevel, logFile)
    global logger
    logger = logging.getLogger('.'.join([__LowerName__, 'root']))
    logger.info("Searching valid profiles within search paths")
    loadProfile()
    parseArguments(sys.argv[1:])
    finalLoggerInit(lg, logLevel, logFile)
    checkCalibrationNeed()
    options.settings = getSettings()
    sa = isServiceAlive()
    if sa is True:
        sa = pauseService('pause')
    # remove temporary directories
    # NOTE: interactive-only
    try:
        os.remove(logFile)
    except OSError as err:
        if err.errno != 2:
            raise
    os.rmdir(tempdir)
    defName = None
    # If necessary settings cannot be found (bad or non existing profiles
    # and no cli integration), log critical error and exit.
    if checkMissingSettings(options.settings.keys()):
        if options.settings['profile'] == 'default':
            options.settings['configure'] = True
            defName = 'default'
        else:
            logger.critical("Missing needed settings!")
            return 11
    # checked till there...OK
    if options.settings['configure'] is True:
        from calise.calibration import CliCalibration
        CliCalibration(defName, brPath=options.settings['path'])
        return 0
    # NOTE: interactive-only from now on ↓
    if os.getenv('DISPLAY') is not None and options.settings['gui'] is True:
        try:
            import calise.QtGui
            rc = calise.QtGui.gui(options.settings)
            if sa is True:
                sa = pauseService('resume')
            return rc
        except ImportError:
            logger.warning(
                'Not able to load Pyqt4 module, using cli-interface')
            options.settings['gui'] = False
    printBriefInfos()
    from calise.ExecThreads import ExecThread
    global trd
    trd = ExecThread(options.settings)
    trd.start()
    cliInterface()
    if sa is True:
        sa = pauseService('resume')
    return 0


if __name__ == '__main__':
    trd = None
    logger = None
    signal.signal(signal.SIGCONT, clear)
    signal.signal(signal.SIGTERM, clear)
    signal.signal(signal.SIGINT, clear)
    signal.signal(signal.SIGTSTP, clear)
    r = main()
    sys.exit(r)
