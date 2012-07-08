#    Copyright (C)   2011   Nicolo' Barbon
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
import time
import threading
import logging
import gobject
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop

from calise import objects
from calise.infos import __LowerName__


# data conversion table
# this is used to convert data coming from dump/dumpAll commands to a more
# human readable form
def setDct():
    global dct
    dct = {
        'amb': "ambient brightness",
        'scr': "screen brightness (avg)",
        'pct': "brightness percentage",
        'cbs': "current backlight step",
        'sbs': "suggested backlight step",
        'cts': "capture timestamp (epoch)",
        'css': "day cycle state",
        'nss': "secs before next day state",
        'slp': "secs between captures",
    }
    sl = 0
    for key in dct.keys():
        tl = len(dct[key])
        if tl > sl:
            sl = tl
    for key in dct.keys():
        dct[key] = "%s: %s" % (dct[key], ' ' * (sl - len(dct[key])))
    return 0


# convert any of 0|'false'|'no' or 1|'true'|'yes' to python False and True
def strToBool(string):
    retVal = None
    if string.lower() in ['0', 'false', 'no']:
        retVal = False
    elif string.lower() in ['1', 'true', 'yes']:
        retVal = True
    return retVal


# Main execution Thread
class whatsmyname(threading.Thread):

    def __init__(self, settings):
        self.logger = logging.getLogger('.'.join([__LowerName__, 'thread']))
        self.logger.info("Starting main Thread...")
        self.objectClass = objects.objects(settings)
        # control "flags"
        self.stop = False
        self.pause = False
        # threading.Thread module initialization
        threading.Thread.__init__(self)

    def run(self):
        ''' Thread core

        Pretty simple:
         - reset working dictionary (all vars to None)
         - execute (execution options all managed by 'settings' var)
         - store the data caoght
         - log what happened
         - sleep (read below for further info about that)

        '''
        self.logger.info("Main Thread successfully started")
        # self.cbs stores current backlight step to make event_logger able to
        # log also first (eventual) backlight change
        self.cbs = self.objectClass.getCbs()
        while self.stop is False:
            self.objectClass.resetComers()
            self.cycle_sleeptime = self.objectClass.executer()
            self.objectClass.append_data()
            self.event_logger()
            # the cycle below sleeps Nth time for 1 sec and meanwhile checks
            # if the stop flag has been set, in that case breaks (and so
            # terminates the thread)
            while self.cycle_sleeptime > time.time():
                # if $pause then sleep indefinitely (until NOT $pause)
                if self.pause is None:
                    self.pause = True
                    while self.pause and not self.stop:
                        time.sleep(1)
                    self.pause = False
                else:
                    time.sleep(1)
                # if $stop then close thread
                if self.stop is True:
                    break

    def event_logger(self):
        objc = self.objectClass
        if len(objc.oldies) == 1:
            if objc.oldies[-1]['cbs'] != self.cbs:
                print objc.oldies[-1]['cbs'], self.cbs
                self.logger.info(
                    "Backlight step changed from %d to %d"
                    % (self.cbs, objc.oldies[-1]['cbs']))
            del self.cbs
            self.logger.info(
                "Time of the day is \"%s\"" % (objc.oldies[-1]['css']))
            self.logger.info(
                "Sleeptime set to %.2f" % (objc.oldies[-1]['slp']))
        elif len(objc.oldies) > 1:
            if objc.oldies[-1]['cbs'] != objc.oldies[-2]['cbs']:
                self.logger.info(
                    "Backlight step changed from %d to %d"
                    % (objc.oldies[-2]['cbs'], objc.oldies[-1]['cbs']))
            if objc.oldies[-1]['css'] != objc.oldies[-2]['css']:
                self.logger.info(
                    "Time of the day changed from \"%s\" to \"%s\""
                    % (objc.oldies[-2]['css'], objc.oldies[-1]['css']))
            if objc.oldies[-1]['slp'] != objc.oldies[-2]['slp']:
                self.logger.info(
                    "Sleeptime between captures changed from %.2f to %.2f"
                    % (objc.oldies[-2]['slp'], objc.oldies[-1]['slp']))
        return 0


class dbusService(dbus.service.Object):

    def __init__(self, pthread, mainLoop, asroot=False):
        setDct()
        self.pth = pthread
        self.mainLoop = mainLoop
        if asroot:
            sbus = dbus.SystemBus
        else:
            sbus = dbus.SessionBus
        self.logger = logging.getLogger('.'.join([__LowerName__, 'service']))
        self.logger.info("Process started with PID %d" % os.getpid())
        self.busObject = 'org.%s.service' % __LowerName__
        self.busPath = '/org/%s/service' % __LowerName__
        bus_name = dbus.service.BusName(self.busObject, bus=sbus())
        dbus.service.Object.__init__(self, bus_name, self.busPath)

    # DBus methods
    # NOTE: Every function regarding thread execution (start, stop, pause,
    #       resume, others) *must* call the wrapper "loggerFuncWrap" and check
    #       the return code.
    #
    @dbus.service.method('org.%s.service' % __LowerName__)
    def kill(self):
        self.logger.debug("Client requested kill. Stopping thread...")
        retCode = self.pth.loggerFuncWrap(self.pth.stopTh)
        if retCode == 0:
            self.logger.info("Sending kill to Dbus-service")
            self.mainLoop.quit()
        # final return code check
        if retCode == 0:
            retMsg = "service successfully stopped"
        else:
            retMsg = (
                "error: \"terminate\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def pause(self):
        self.logger.debug("Client requested pause. Pausing thread...")
        retCode = self.pth.loggerFuncWrap(self.pth.pauseTh)
        # final return code check
        if retCode == 0:
            retMsg = "service successfully paused"
        else:
            retMsg = (
                "error: \"pause\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def resume(self):
        self.logger.debug("Client requested resume. Resuming thread...")
        retCode = self.pth.loggerFuncWrap(self.pth.resumeTh)
        # final return code check
        if retCode == 0:
            retMsg = "service successfully resumed"
        else:
            retMsg = (
                "error \"resume\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def restart(self):
        self.logger.debug("Client requested restart. Stopping thread...")
        retCode = self.pth.loggerFuncWrap(self.pth.stopTh)
        if retCode == 0:
            self.logger.debug(
                "Client requested restart. Starting a new thread...")
            retCode = self.pth.loggerFuncWrap(self.pth.startTh)
        # final return code check
        if retCode == 0:
            retMsg = "service successfully restarted"
        else:
            retMsg = (
                "error: \"restart\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def start(self):
        self.logger.debug("Client requested start. Starting thread...")
        retCode = self.pth.loggerFuncWrap(self.pth.startTh)
        # final return code check
        if retCode == 0:
            retMsg = "service successfully started"
        else:
            retMsg = (
                "error: \"start\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def stop(self):
        self.logger.debug("Client requested stop. Stopping thread...")
        retCode = self.pth.loggerFuncWrap(self.pth.stopTh)
        # final return code check
        if retCode == 0:
            retMsg = "service successfully stopped"
        else:
            retMsg = (
                "warning: \"stop\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def check(self):
        self.logger.debug("Client requested check. Checking thread...")
        retCode = self.pth.loggerFuncWrap(self.pth.checkTh)
        # final return code check
        if retCode == 0:
            retMsg = "service is alive and running"
        elif retCode == 2:
            retMsg = "service is alive but paused"
        else:
            retMsg = (
                "warning: unable to check thread execution")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def dump(self):
        self.logger.debug("Client requested dump. Dumping data...")
        retVal = self.pth.dumpTh()
        if retVal:
            vals = retVal
            retMsg = (
                '\n'.join(['%s%s' % (dct[k], vals[k]) for k in vals.keys()]))
            self.logger.debug("Data dumped")
        else:
            retMsg = (
                "warning: \"dump\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def dumpall(self):
        self.logger.debug("Client requested dumpAll. Dumping all data...")
        retVal = self.pth.dumpallTh()
        if retVal:
            vals = {}
            for idx in range(len(retVal)):
                for key in retVal[idx].keys():
                    if vals.keys().count(key):
                        vals[key] += [retVal[idx][key]]
                    else:
                        vals[key] = [retVal[idx][key]]
            retMsg = (
                '\n'.join(['%s%s' % (dct[k], vals[k]) for k in vals.keys()]))
            self.logger.debug("All data dumped")
        else:
            retMsg = (
                "warning: \"dump all\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def dumpsettings(self):
        self.logger.debug("Client requested dump settings. Dumping data...")
        retVal = self.pth.dumpsettingsTh()
        if retVal:
            args = retVal
            retMsg = '\n'.join(['%s: %s' % (k, args[k]) for k in args.keys()])
            self.logger.debug("Settings dumped")
        else:
            retMsg = (
                "warning: \"dump settings\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def capture(self):
        self.logger.debug("Client requested manual capture. Capturing...")
        retCode = self.pth.thCapture()
        # final return code check
        if retCode == 0:
            retMsg = "manual capture successfully executed"
        else:
            retMsg = (
                "warning: \"manual capture\" not processed correctly, "
                "read program logs for further info")
        return retMsg

    @dbus.service.method('org.%s.service' % __LowerName__)
    def settingset(self, idx, value):
        self.logger.debug("Client requested %s setting. Processing..." % idx)
        retCode = self.pth.setTh(idx, str(value))
        # final return code check
        if retCode == 0:
            retMsg = "%s successfully set to %s" % (idx, value)
        else:
            retMsg = (
                "warning: \"%s\" setting not processed correctly, "
                "read program logs for further info" % idx)
        return retMsg


class methodHandler():

    # non-Dbus related initializations
    def __init__(self, settings):
        self.logger = logging.getLogger('.'.join([__LowerName__, 'handler']))
        # var setting
        self.settings = settings
        self.th = None  # service thread

    # Thread execution related functions
    # NOTE: function name should be same as calling command's name with
    #       appended "Th", for example "stop" command should find function
    #       named "stopTh"
    # NOTE: retrun codes '0' and '2' mean a somehow successful operation,
    #       others are considered errors
    def loggerFuncWrap(self, func):
        rc = func()
        if rc in (0, 2):
            self.logger.info(
                "\"%s thread\" successfully processed"
                % (func.__name__[:-2].title())
            )
        else:
            self.logger.error(
                "Failed to process \"%s thread\", error code: %d"
                % (func.__name__[:-2], rc)
            )
        return rc

    # start thread execution
    def startTh(self):
        if self.th is not None:
            if self.th.isAlive():
                return 2
        self.th = whatsmyname(self.settings)
        self.th.start()
        if self.th.isAlive():
            return 0
        return 1

    # stop thread execution
    def stopTh(self):
        if self.th is not None:
            if self.th.isAlive():
                self.th.stop = True
                joinTime = (
                    self.th.objectClass.arguments['capnum'] *
                    self.th.objectClass.arguments['capint'] * 3)
                if joinTime < 5:
                    joinTime = 5
                self.th.join(joinTime)
                if self.th.isAlive():
                    self.th = None
                    return 1
        return 0

    # pause thread execution
    def pauseTh(self):
        if self.th is not None:
            if self.th.isAlive() and self.th.pause is False:
                self.th.pause = None
                while self.th.pause is not True:
                    time.sleep(0.1)
                return 0
        return 1

    # resume thread execution
    def resumeTh(self):
        if self.th is not None:
            if self.th.isAlive() and self.th.pause is True:
                self.th.pause = None
                while self.th.pause is not False:
                    time.sleep(0.1)
                return 0
        return 1

    # check thread execution
    # If alive but paused returns 2, else if Alive and not paused, 0.
    def checkTh(self):
        if self.th is not None:
            if self.th.isAlive():
                if self.th.pause is True:
                    retCode = 2
                else:
                    retCode = 0
            else:
                retCode = 3
        else:
            retCode = 1
        return retCode

    # dump data
    def dumpTh(self):
        vals = self.th.objectClass.dumpValues()
        return vals

    # dump all data
    def dumpallTh(self):
        vals = self.th.objectClass.dumpValues(allv=True)
        return vals

    # dump settings
    def dumpsettingsTh(self):
        args = self.th.objectClass.arguments
        return args

    # Manual camera capture
    # If an existing running thread is found it will be paused and then
    # resumed else, a temporary thread is initialized (but not started)
    def thCapture(self):
        r = self.checkTh()
        if r in (0, 2):
            if r == 0:
                self.pauseTh()
            self.th.objectClass.resetComers()
            old = self.th.objectClass.oldies[-1]
            w = self.th.objectClass.writeStep(standalone=True)
            ts = self.th.objectClass.newcomers['cts'] - old['cts']
            self.th.objectClass.newcomers['nss'] = old['nss'] - ts
            self.th.objectClass.newcomers['slp'] = old['slp'] - ts
            self.th.objectClass.newcomers['css'] = old['css']
            self.th.objectClass.append_data()
            self.th.event_logger()
            if r == 0:
                self.resumeTh()
        else:
            if r == 1:
                self.th = whatsmyname()
            w = self.th.objectClass.writeStep(standalone=True)
            self.th.event_logger()
        self.logger.debug("Function objects.writeStep returned %d" % w)
        return 0

    # Set thread variable's value (one per call)
    # every and only settings stated there can be changed during execution
    # TODO: simplify removing actual key names
    def setTh(self, idx, value):
        retCode = 0
        if idx in ['geoip']:
            value = strToBool(value)
            self.settings['geoip'] = value
            self.th.objectClass.arguments['geoip'] = value
        elif idx in ['weather']:
            value = strToBool(value)
            self.settings['weather'] = value
            self.th.objectClass.arguments['weather'] = value
        elif idx in ['screen']:
            value = strToBool(value)
            self.settings['screen'] = value
            self.th.objectClass.arguments['screen'] = value
        elif idx in ['latitude']:
            value = float(value)
            self.settings['latitude'] = value
            self.th.objectClass.arguments['latitude'] = value
        elif idx in ['longitude']:
            value = float(value)
            self.settings['longitude'] = value
            self.th.objectClass.arguments['longitude'] = value
        elif idx in ['capnum']:
            value = int(value)
            self.settings['capnum'] = value
            self.th.objectClass.arguments['capnum'] = value
        elif idx in ['capint']:
            value = float(value)
            self.settings['capint'] = value
            self.th.objectClass.arguments['capint'] = value
        elif idx in ['dayst']:
            value = float(value)
            self.settings['dayst'] = value
            self.th.objectClass.arguments['dayst'] = value
        elif idx in ['dusksm']:
            value = float(value)
            self.settings['dusksm'] = value
            self.th.objectClass.arguments['dusksm'] = value
        elif idx in ['nightst']:
            value = float(value)
            self.settings['nightst'] = value
            self.th.objectClass.arguments['nightst'] = value
        else:
            retCode = 1
            self.logger.warning(
                "\"%s\" cannot be set while the service is running" % idx)
        if retCode == 0:
            self.logger.debug(
                "\"%s\" setting to %s successfully processed" % (idx, value))
        return retCode


class service():

    def __init__(self, settings, isroot=False):
        self.isroot = isroot
        self.serviceHandler = methodHandler(settings)
        # NOTE: thread start on init by default, to avoid comment line below
        self.serviceHandler.loggerFuncWrap(self.serviceHandler.startTh)
        # bus initialization
        self.initServiceBus()

    def initServiceBus(self):
        DBusGMainLoop(set_as_default=True)
        self.loop = gobject.MainLoop()
        gobject.threads_init()
        serviceBus = dbusService(self.serviceHandler, self.loop, self.isroot)

    def runLoop(self):
        self.loop.run()
