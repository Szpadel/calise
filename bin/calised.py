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

import os
import sys
import logging
import tempfile
import dbus

from calise.infos import __LowerName__
from calise import optionsd as options
from calise.dbusService import service
from calise.extServiceFunctions import getDbusSession, tempUtils, clearTempdir


# Since all commands listed under serviceCommands make sense only with a
# service instance running, if present otherwise the help screen will show
# instead.
def checkServiceCommands(arglist):
    exitCode = None
    for cmd in options.serviceCommands:
        if arglist.count('check'):
            print "service is not alive"
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
    # Set 'niceness' level to 10 if process has not been 'niced' by the user
    niceness = os.nice(0)
    if niceness == 0:
        niceness = os.nice(10)
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


def queryService(cbus, queryArgs, execArgs):
    bus = cbus()
    busObject = 'org.%s.service' % __LowerName__
    busPath = '/org/%s/service' % __LowerName__
    # try to connect to service DBus object
    try:
        service = bus.get_object(busObject, busPath)
    except dbus.exceptions.DBusException as err:
        if err.get_dbus_name() == \
            'org.freedesktop.DBus.Error.ServiceUnknown':
            return 21
        else:
            raise
    # "set setting" command processing
    for setting in options.settings:
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
    for command in queryArgs + execArgs:
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
    return 0


def main():
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
    if tmp == 0:
        # valid tempdir found (means success!)
        # remove default profile setting since it cannot be changed during
        # service execution
        del options.settings['profile']
        # check if no arguments are being passed
        if not options.settings.keys() + ap.serviceArgs.keys():
            print(
                "%s: error: a service instance should be already running"
                % sys.argv[0])
            return 6
        tu.getpuid(tu.pid)
        if tu.uid is None:
            # process terminated without clearing
            clearTempdir(tu.pidfile)
            return 20
        elif tu.uid == 0:
            # process started by root
            sbus = dbus.SystemBus
        elif tu.uid == os.getuid():
            # process owner is current user
            sbus = dbus.SessionBus
        elif tu.uid != 0 and os.getuid() == 0:
            # process not started by root and current user is root
            import pwd
            user = pwd.getpwuid(tu.uid)[0]  # username of given UID
            dbs = getDbusSession(user, os.getenv('DISPLAY'))
            if dbs:
                # DBus session found
                os.environ['DBUS_SESSION_BUS_ADDRESS'] = dbs
                os.setuid(tu.uid)
                sbus = dbus.SessionBus
            else:
                # no DBus sessions found
                return 40
        else:
            # service started by another (non-root) user
            print(
                "%s: error: the service was started by another user"
                % sys.argv[0])
            return 22
        # query DBus bus
        qs = queryService(sbus, ap.queryArgs.keys(), ap.execArgs.keys())
        if qs == 21:
            clearTempdir(tu.pidfile)
        return qs

    elif tmp == 1:
        # no temporary folders, start new service session
        ms = mainService(ap)
        return ms

    elif tmp == 3:
        # unable to access a probable tempdir
        return tmp

    elif tmp == 12:
        # no pidfile inside checked workdir (should be impossible to obtain)
        return tmp

    elif tmp == 13:
        # .pid file cannot contain a valid process ID (not a numeric integer)
        return tmp

    else:
        # unexpected error code, quit please...
        return tmp


if __name__ == '__main__':
    sys.exit(main())
