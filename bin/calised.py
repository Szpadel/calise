#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
#    Calise - CameraLightSensorProject
#             calculates ambient brightness and suggests (or sets)
#             screen's correct backlight level using a camera.
#
#    Copyright (C)   2011   Nicolo' Barbon
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

import os
import sys
import logging
import tempfile
import dbus

from calise.infos import __LowerName__
from calise import optionsd as options
from calise.dbusService import service


class tempUtils():

    def __init__(self):
        self.workdir = None     # service tempdir (str)
        self.pidfile = None     # service PID file (str)
        self.pid = None         # service process ID (int)
        self.uid = None         # service owner's user ID (int)

    # read PID file (pf) and obtain service process ID
    def getpidfromfile(self, pf=None):
        retCode = 1
        # input control
        if pf is None and self.pidfile is not None:
            pf = self.pidfile
        elif pf is None and self.pidfile is None:
            retCode = 2
        # function body
        if pf:
            try:
                with open(pf, 'r') as fp:
                    pid = fp.read().splitlines()[0]
                    pid = int(pid)
                    self.pid = pid
                    retCode = 0
            except ValueError:
                retCode = 3
        return retCode

    # obtain a possible service-tempdir and check if it's so
    def obtainWorkdir(self, tempre='%s-' % __LowerName__):
        retCode = 1
        ext = '.pid'
        for item in os.listdir(tempfile.gettempdir()):
            pre_len = len(tempre)
            if item[:pre_len] == tempre and len(item) == pre_len + 6:
                workdir = os.path.join(tempfile.gettempdir(), item)
                try:
                    for item in os.listdir(workdir):
                        if (
                            item[:pre_len] == tempre and
                            len(item) == pre_len + 6 + len(ext) and
                            item[-len(ext):] == ext):
                            pidfile = os.path.join(workdir, item)
                            cc = self.getpidfromfile(pidfile)
                            if 0 == cc:
                                self.workdir = workdir
                                self.pidfile = pidfile
                                retCode = 0
                            else:
                                retCode = cc + 10
                            break
                except OSError as err:
                    if err.errno == 13:
                        retCode = 3
        return retCode

    # get PID's owner user ID
    def getpuid(self, pid):
        retCode = 1
        # input control
        if pid is None and self.pid is not None:
            pid = self.pid
        elif pid is None and self.pid is None:
            retCode = 2
        # function body
        if pid:
            try:
                with open('/proc/%d/status' % pid, 'r') as fp:
                    for ln in fp.readlines():
                        if ln.startswith('Uid:'):
                            uid = int(ln.split()[1])
                            self.uid = uid
            except IOError as err:
                if err.errno == 2:
                    pass
        return retCode


# function that clear calise tempdir eventually left behind from unexpected
# program end
def clearTempdir(pid):
    print(
        "%s: warning: PID found but no running service "
        "instances." % sys.argv[0])
    for tf in os.listdir(os.path.dirname(pid)):
        os.remove(os.path.join(os.path.dirname(pid), tf))
    os.rmdir(os.path.dirname(pid))
    print(
        "Folder %s has been removed will all its contents"
        % os.path.dirname(pid))


# Since all commands listed under serviceCommands make sense only with a
# service instance running, if present otherwise the help screen will show
# instead.
def checkServiceCommands(arglist):
    exitCode = None
    for cmd in options.serviceCommands:
        if arglist.count('check'):
            print "Service is not alive"
            exitCode = 1
            break
        elif arglist.count(cmd):
            hp = options.serviceGetArgs([])
            hp.init_args()
            hp.parser.print_usage()
            sys.stderr.write("%s: error: start service first\n" % sys.argv[0])
            print(
                "Internal argument \"%s\" make sense only with a service "
                "instance running." % cmd)
            exitCode = 2
            break
    if exitCode is not None:
        sys.exit(exitCode)


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


# Check for duplicates execution commands (eg. pause and resume together)
def checkExecArguments(args):
    retCode = 0
    if type(args) != dict:
        retCode = 2
    else:
        arglist = []
        counter = 0
        for command in options.execCommands:
            if args.keys().count(command):
                arglist.append(command)
                counter += 1
        if counter > 1:
            retCode = (1, arglist)
    return retCode


# service-start function
def mainService(kargs):
    retCode = 0
    # Check for arguments inadmissibility
    checkServiceCommands(kargs.args.keys())
    # Leave only profile setting on settings global so that when
    # options.profiler executes, it has no existing settings (which, due to
    # function behaviour, won't overwrite)
    # TODO: Fix that please... it's nogood
    for key in options.settings.keys():
        if key != 'profile':
            del options.settings[key]
    # Temporary paths initialization
    tempdir = tempfile.mkdtemp(prefix='%s-' % __LowerName__)
    logObject = tempfile.NamedTemporaryFile(
        prefix='%s-' % os.path.join(tempdir, __LowerName__), delete=False)
    # setting-related operations
    defaults = options.getDefaultSettings()
    options.settings['logfile'] = logObject.name
    logLevel = defaults['loglevel']
    logFile = logObject.name
    lg = options.wlogger(logLevel, logFile)
    logger = logging.getLogger('.'.join([__LowerName__, 'root']))
    # Obtain valid profile
    pf = options.profiler()
    logger.info("Searching valid profiles within search paths")
    for cf in options.get_path(options.settings['profile']):
        pf.check_config(cf)
    # Parse arguments (seriously this time)
    kargs.init_args()
    kargs.parse_settings()
    options.checkSettingsArguments()
    if logLevel != options.settings['loglevel']:
        if checkLogLevelSyntax(options.settings['loglevel'], logLevel):
            options.settings['loglevel'] = logLevel
        else:
            lg.changeLogLevel(options.settings['loglevel'])
    if logFile != options.settings['logfile']:
        if checkLogFileSyntax(options.settings['logfile'], logFile):
            options.settings['logfile'] = logFile
        else:
            # copy temporary contents (pre-profile reading log) to the
            # new logfile specified in the profile just read
            with open(logFile, 'r') as fp:
                rp = fp.read()
            os.remove(logFile)
            with open(options.settings['logfile'], 'a') as fp:
                fp.write(rp)
        lg.changeLogFile(options.settings['logfile'])
    # If necessary settings cannot be found (bad or non existing profiles
    # and no cli integration), log critical error and exit.
    if checkMissingSettings(options.settings.keys()):
        logger.critical("Missing needed settings!")
        retCode = 11
    else:
        # Generate PID
        pid = os.getpid()
        pidfile = tempfile.NamedTemporaryFile(
            prefix='%s-' % os.path.join(tempdir, __LowerName__),
            suffix='.pid', delete=False)
        with pidfile:
            pidfile.write('%i\n' % pid)
        # Set tempfile permission to a+r
        os.chmod(tempdir, 0755)
        os.chmod(pidfile.name, 0644)
        if os.path.isfile(logFile):
            os.chmod(logFile, 0644)
        # Start service
        ms = service(options.settings, not bool(os.getuid()))
        ms.runLoop()
        # Exit cleanage
        if os.path.isfile(logFile):
            os.remove(logFile)
        os.remove(pidfile.name)
        os.rmdir(tempdir)


def main():
    retCode = 0
    # Arguments parse
    ap = options.serviceGetArgs(sys.argv[1:])
    ap.init_args()
    ap.parse_settings()
    # critical errors checks
    rc = checkExecArguments(ap.execArgs)
    if type(rc) == tuple:
        print(
            "critical: Commands %s cannot be executed together."
            % " and ".join([", ".join(rc[1][1:]), rc[1][0]]))
        return 5
    elif rc != 0:
        print(
            "critical: This error should never happen, you're *lucky*!")
        return 30
    # "normal" behaviour
    tu = tempUtils()
    tmp = tu.obtainWorkdir()
    # client query
    # if service is active, cli arguments are managed as execution commands
    if tmp == 0:
        tu.getpuid(tu.pid)
        # choose DBus bus between Session and System
        # if process with pid doesn't exist (and so doesn't uid) means that
        # process terminated unexpectedly and left behind temporary dir
        if tu.uid is None:
            clearTempdir(tu.pidfile)
            return 20
        elif tu.uid == 0:
            sbus = dbus.SystemBus
        elif tu.uid == os.getuid() or os.getuid() == 0:
            sbus = dbus.SessionBus
            # root is able to control every service instance (whoever user
            # started it)
            if os.getuid() == 0:
                os.setuid(tu.uid)
        else:
            print(
                "%s: error: the service was started by another user"
                % sys.argv[0])
            return 22
        # connection to the selected DBus bus
        bus = sbus()
        busObject = 'org.%s.service' % __LowerName__
        busPath = '/org/%s/service' % __LowerName__
        # try to connect to service DBus object
        try:
            service = bus.get_object(busObject, busPath)
        except dbus.exceptions.DBusException as err:
            if err.get_dbus_name() == \
                'org.freedesktop.DBus.Error.ServiceUnknown':
                clearTempdir(tu.pidfile)
                return 21
            else:
                raise
        # "set setting" command processing
        for setting in options.settings:
            if setting != 'profile':
                ans = service.get_dbus_method('settingset', busObject)
                try:
                    print ans(setting, options.settings[setting])
                except dbus.exceptions.DBusException as err:
                    if err.get_dbus_name() == \
                        'org.freedesktop.DBus.Error.AccessDenied':
                        print(
                            "warning: you are not allowed to set "
                            "settings inside the service")
        # "service execution" command processing
        for command in ap.queryArgs.keys() + ap.execArgs.keys():
            ans = service.get_dbus_method(command, busObject)
            try:
                print ans()
            except dbus.exceptions.DBusException as err:
                if err.get_dbus_name() == \
                    'org.freedesktop.DBus.Error.AccessDenied':
                    print(
                        "warning: you are not allowed to send "
                        "command \"%s\" to the service" % command)
                elif err.get_dbus_name() == \
                    'org.freedesktop.DBus.Python.IndexError':
                    print(
                        "warning: there is no data to dump, retry later")
    # service start
    # if there's no service active, cli arguments are managed as start
    # options
    elif tmp in (1,):
        retCode = mainService(ap)
    return retCode


if __name__ == '__main__':
    sys.exit(main())
