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
import re
import errno
import tempfile

from calise.infos import __LowerName__


def getDbusSession(user, display=None):
    ''' Get process's owner 'DBUS_SESSION_BUS_ADDRESS' address

    To send signals to a DBus session-bus from outside (session), session's
    user dbus directory inside home folder has to be read to obtain
    enviroment variable 'DBUS_SESSION_BUS_ADDRESS', from the files there.

    '''
    retVal = None
    displayProg = re.compile('.*\#[ a-zA-Z]+(:[0-9.]+).*', re.DOTALL)
    busProg = re.compile('.*DBUS_SESSION_BUS_ADDRESS=([^\n]+)', re.DOTALL)
    for bus in os.listdir('/home/%s/.dbus/session-bus/' % user):
        with open('/home/%s/.dbus/session-bus/%s' % (user, bus)) as fp:
            cont = fp.read()
        a = displayProg.match(cont)
        if a is not None:
            if (
                (not display and a.group(1).startswith(':0')) or
                (a.group(1) == display)
            ):
                a = busProg.match(cont)
                if a is not None:
                    retVal = a.group(1)
    return retVal


# Manager for all temporary directory related things
class tempUtils():

    def __init__(self):
        self.workdir = None     # service tempdir (str)
        self.pidfile = None     # service PID file (str)
        self.pid = None         # service process ID (int)
        self.uid = None         # service owner's user ID (int)

    def obtainWorkdir(self, tempre='%s-' % __LowerName__):
        ''' obtain a possible service-tempdir and check if it's so

        Return codes:
              0: both "workdir" and "pidfile" class variables has been stored
              1: generic error (there shouldn't be any tempdir)
              3: file access error
            >10: "getpidfromfile" function error (to get "getpidfromfile",
                 subtract 10)
        '''
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
                    if err.errno == errno.EACCES:
                        retCode = 3
        return retCode

    def getpidfromfile(self, pf=None):
        ''' Read PID file (pf) and obtain service process ID

        Return codes:
              0: "pid" class variable has been stored
              1: generic error
              2: there's no pidfile to be used as source (not stored nor given)
              3: file content cannot be a process id (not numeric integer)
        '''
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

    def getpuid(self, pid):
        ''' Get PID's owner user ID

        Return codes:
              0: "uid" class variable has been stored
              1: genric error / requested process with id $pid is not running
              2: there's no process id to check (not stored nor given)
        '''
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
                            retCode = 0
            except IOError as err:
                if err.errno == 2:
                    pass
        return retCode


def clearTempdir(pid):
    ''' Delete temporary directory

    Function that clears calise tempdir eventually left behind from unexpected
    program end.
    Since it has no own controls, must be run after a check stated that the
    program really exited unexpectedly leaving behind temporary directories.

    '''
    print(
        "%s: warning: PID found but no running service "
        "instances." % sys.argv[0])
    for tf in os.listdir(os.path.dirname(pid)):
        os.remove(os.path.join(os.path.dirname(pid), tf))
    os.rmdir(os.path.dirname(pid))
    print(
        "Folder %s has been removed will all its contents"
        % os.path.dirname(pid))
