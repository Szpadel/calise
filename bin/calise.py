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

import gettext, locale
import sys
import os.path
from xdg.BaseDirectory import save_config_path
import tempfile

from subprocess import Popen, PIPE

from calise.infos import __LowerName__, __version__, __CapitalName__


try:
    locale.setlocale(locale.LC_ALL, '')
    gettext.bindtextdomain( __LowerName__)
    gettext.textdomain(__LowerName__)
    gettext.install(__LowerName__, unicode=False)
except locale.Error, err:
    sys.stderr.write(err)


def obtainWorkdir(tempre="%s-" % __LowerName__):
    # crappy way to obtain current temporary workdir...
    pid = None
    for item in os.listdir(tempfile.gettempdir()):
        pre_len = len(tempre)
        if item[:pre_len] == tempre and len(item) == pre_len + 6:
            workdir = os.path.join(tempfile.gettempdir(), item)
            for item in os.listdir(workdir):
                if (
                    item[:pre_len] == tempre and\
                    len(item) == pre_len + 10 and\
                    item[-4:] == ".pid"):
                    pid = os.path.join(workdir, item)
            break
    return pid


if __name__ == '__main__':

    import signal
    import calise.options

    global trd
    trd = None
    arguments = None

    # manages clean exit/pause
    def clear(sig=None, func=None):
        if sig == signal.SIGTERM or sig == signal.SIGINT:
            if trd is not None:
                trd.func.sig = 'quit'
                for x in range(20):
                    if not trd.isAlive(): break
                    sleep(0.1)
                    if x == 19:
                        os.kill(os.getpid(), signal.SIGKILL)
            sys.exit(sig)
        elif sig == signal.SIGTSTP:
            if trd is not None: trd.func.sig = 'pause'
        elif sig == signal.SIGCONT:
            if trd is not None: trd.func.sig = 'resume'
        elif sig == signal.SIGUSR1:
            if arguments is not None:
                if arguments.logdata is False: arguments.logdata = True
                else: arguments.logdata = False
        elif sig == signal.SIGUSR2:
            if trd is not None: trd.func.sig = 'export'

    calise.options.argsparser(version=__version__)
    if not calise.options.arguments.verbosity:
        print(
            '%s-%s (C) 2011 Nicolo\' Barbon\n'
            % (__CapitalName__,__version__)
        )

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
        pcs = Popen(['calised', '--pause'], stdout=PIPE, stderr=PIPE)
        dmp = pcs.communicate()
        if ''.join(dmp[0].split('\n')).startswith("warning: "):
            print(
                "Unable to pause a running calised execution, calise won't"
                "start because it's higly probable that the two programs"
                "will overlap")
            sys.exit(7)
        else:
            service_wasAlive = True
    # service alive and paused
    elif ''.join(dmp[0].split('\n')) == "service is alive but paused":
        pass
    # service is not alive
    elif ''.join(dmp[0].split('\n')) == "service is not alive":
        pass
    # warning: unable to check service execution
    elif ''.join(dmp[0].split('\n')).startswith("warning: "):
        pass


    defName = 'default'
    defConf = '%s.conf' % os.path.join(
        save_config_path(__LowerName__), defName)
    sysConf = '%s.conf' % os.path.join(os.path.join('/', 'etc', __LowerName__))
    if not os.path.isfile(defConf) and not os.path.isfile(sysConf):
        from calise.calibration import CliCalibration
        CliCalibration(defName, brPath=calise.options.arguments.path)
        sys.exit(0)
    elif calise.options.arguments.cal:
        from calise.calibration import CliCalibration
        CliCalibration(brPath=calise.options.arguments.path)
        sys.exit(0)
    calise.options.ParseCfgFile()
    arguments = calise.options.arguments

    # brief check for non-assigned arguments (and set them to default)
    if arguments.auto is None:
        arguments.auto = True
    if arguments.screen is None and os.getenv('DISPLAY') is not None:
        arguments.screen = True
    else:
        arguments.screen = False
    if not arguments.logdata:
        arguments.logdata = False
    if arguments.gui is None:
        arguments.gui = True
    # CPU usage will start decreasing slower from the two time values
    # set as default, so they're the best points to pick
    if not arguments.gap:
        if arguments.screen is True:
            arguments.gap = 0.8 # best with screencapture
        elif not arguments.screen:
            arguments.gap = 0.6 # best without
    # averaging "time", good range is from 60 to 120 (1 or 2 minutes)
    if not arguments.avg:
        sgv = 90
        arguments.avg = int( sgv / float(arguments.gap) )

    if os.getenv('DISPLAY') is not None and arguments.gui is not False:
        try:
            import calise.QtGui
            calise.QtGui.gui(arguments)
            sys.exit(0)
        except ImportError, err:
            print err
            arguments.gui = False
            arguments.screen = False

    signal.signal(signal.SIGCONT, clear)
    signal.signal(signal.SIGTERM, clear)
    signal.signal(signal.SIGINT, clear)
    signal.signal(signal.SIGTSTP, clear)
    signal.signal(signal.SIGUSR1, clear)
    signal.signal(signal.SIGUSR2, clear)

    if not arguments.verbosity:
        strt = []
        for step in range(arguments.bkofs, arguments.steps+arguments.bkofs):
            strt.append(str(step))
            if arguments.invert: strt.reverse()
        print(
            (
                _("Using \"%s\" profile") + "\n" +
                _("Camera") + ": %s\n" +
                _("Sysfs backlight path") + ": %s\n" +
                _("Backlight steps") + ": %s\n" +
                _("Delta and offset") + ": %.3f, %.1f\n" +
                _("Time gap") + ": %.2f\n" +
                _("Number of values to average") + ": %d"
            ) % (
                arguments.profile,
                arguments.cam,
                arguments.path.rstrip('/' + os.path.basename(arguments.path)),
                ' -> '.join([strt[0],strt[-1]]),
                arguments.delta,
                arguments.ofs,
                arguments.gap,
                arguments.avg
            )
        )
    if arguments.verbosity == 1:
        argList = [
            ('version',__version__),
            ('profile',arguments.profile),
            ('cam',arguments.cam),
            ('path',arguments.path),
            ('steps',arguments.steps),
            ('bkofs',arguments.bkofs),
            ('delta',arguments.delta),
            ('ofs',arguments.ofs),
            ('gap',arguments.gap),
            ('avg',arguments.avg),
        ]
        print argList


    from calise.ExecThreads import ExecThread
    trd = ExecThread(arguments)
    trd.start()

    if (
        (os.getenv('DISPLAY') is None or arguments.gui is False) and 
        not arguments.verbosity):
        '''Interactive interface commands:
        q) exits, e) exports data, p) pauses/resumes, a) starts/stops collecting
        data
        '''
        from calise.getkey import _Getch
        getch = _Getch()
        while trd.isAlive():
            try: ch = getch()
            except IOError as err:
                if err.errno == 4: ch = '0'
            if ch in 'qQ':
                trd.func.sig = 'quit'
                from time import sleep
                for x in range(20):
                    if not trd.isAlive(): break
                    sleep(0.1)
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
                if arguments.logdata is False: arguments.logdata = True
                else: arguments.logdata = False
        print ''
    else:
        # Temporary solution until I have time to write something good
        from time import sleep
        while trd.isAlive(): sleep(0.5)


    # NOTE: Right now the program isn't aware of the options given to the
    #       service, so it will start a "default" instance, that means it will
    #       read from "default" profile
    if service_wasAlive:
        p = Popen(['calised', '--resume'], stdout=PIPE, stderr=PIPE)
        ret = p.communicate()
