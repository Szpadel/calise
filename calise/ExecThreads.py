# -*- coding: utf-8 -*-
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
import time
import threading

from calise.capture import imaging
from calise.system import execution


class ExecThread(threading.Thread):

    def __init__(self, args):
        self.func = mainLoop(args)
        threading.Thread.__init__(self)

    def run(self):
        self.func.main()


class mainLoop():

    def __init__(self, args):
        self.step0 = None # capture class
        self.step1 = None # execution class
        self.lock = None
        self.ValuesAverage = 0
        self.sig = '' # signal: can be either quit, pause, resume or export
        self.timeref = None
        self.basetime = None
        self.sct = 5 # seconds between screencaptures:
                     # it's useless to capture the whole screen more often,
                     # maybe it can increased
        self.args = args
        self.ExpPath = self.args.logpath # data export path


    '''checks how much time passed from loop start and sleeps so that the
    entire cycle duration is 'self.args.gap', if that is not possible
    (time passed > self.args.gap), doesn't sleeps.
    Also checks if there are signals waiting to be processed
    '''
    def drowsiness(self):
        sleeptime = 0.01
        iternum = (self.args.gap + self.timeref - time.time()) / sleeptime
        if iternum < 1:
            iternum = 1
        for x in range(int(round(iternum, 0))):
            # QUIT
            if self.sig == 'quit':
                return True
            # PAUSE / RESUME
            elif self.sig == 'pause':
                self.step0.stopCapture()
                if not self.args.gui:
                    sys.stdout.write('\n  =====  PAUSE  =====  \r')
                    sys.stdout.flush()
                while self.sig is not 'resume':
                    if self.sig == 'quit':
                        return True
                    elif self.sig == 'export':
                        self.WriteLog()
                        self.sig='pause'
                    time.sleep(sleeptime)
                if self.sig is not 'quit':
                    self.step0.startCapture()
            # EXPORT
            elif self.sig == 'export':
                self.WriteLog()
                self.sig = ''
            else:
                time.sleep(sleeptime)
        return False

    '''merges data from history (if available) and current average-range, then
    formats as Comma Separated Values and saves to current dir as "calise.csv"
    '''
    def WriteLog(self):
        log = (
            'Timestamp,'
            'Ambient,Screen,Correction,RawAmbient,'
            'Percentage,Step,RealStep\n'
        )
        dictionaries = [self.step1.history]
        for dictionary in dictionaries:
            for idx in range(len(dictionary['ambient'])):
                log += (
                    '%f,'
                    '%d,%d,%f,%d,'
                    '%f,%d,%d\n'
                    % (
                        round(dictionary['timestamp'][idx-1],2),
                        int(
                            dictionary['ambient'][idx-1] -
                                dictionary['correction'][idx-1]
                        ),
                        int(dictionary['screen'][idx-1]),
                        round(dictionary['correction'][idx-1],2),
                        int(dictionary['ambient'][idx-1]),
                        round(dictionary['percent'][idx-1],1),
                        int(dictionary['step'][idx-1]),
                        int(dictionary['bkstp'][idx-1])
                    )
                )
        if self.ExpPath is None:
            self.ExpPath = '.'.join(['calise','csv'])
        if os.path.basename(self.ExpPath).split('.')[-1] != 'csv':
            self.ExpPath = '.'.join([self.ExpPath,'csv'])
        try:
            with open(self.ExpPath, 'w') as fd:
                fd.write(log)
        except:
            print( '\n' + _('Unable to export to "%s"') % (self.ExpPath) )

    def mainOp(self):
        self.step0 = imaging()
        self.step1 = execution(
            self.args.steps,
            self.args.bkofs,
            self.args.invert,
            self.args.ofs,
            self.args.delta,
            pos = self.args.path,
        )
        self.lock = _locker()
        self.basetime = time.time() - self.sct
        self.step0.initializeCamera(self.args.cam)
        self.step0.startCapture()
        self.step0.getFrameBriSimple()

    def mainEd(self):
        self.step0.stopCapture()
        self.step0.freeCameraObj()

    def exeloop(self):
        self.timeref = time.time() # start time of the loop
        self.step0.getFrameBriSimple()
        if (
            self.args.screen is True and
            self.basetime + self.sct <= time.time()
            ):
            self.step0.getScreenBri()
            self.basetime = time.time()
        elif self.args.screen is None:
            self.step0.scr = 0.0
        self.step1.elaborate(self.step0.amb, self.step0.scr)
        if (
            ( self.args.auto ) and
            (
                self.lock.lock is False or
                len(self.step1.data['percent']) < 15 or
                abs(
                    self.step1.data['step'][-1] -
                    self.step1.data['bkstp'][-1]
                ) > 1
            )
        ):
            if self.step1.WriteStep() is True:
                self.lock.put()
        self.step1.PopDataValues(self.args.avg)
        if self.args.logdata:
            for val in self.step1.data:
                self.step1.history[val].append( self.step1.data[val][-1] )

        self.ValuesAverage = (
            sum(self.step1.data['percent'])/len(self.step1.data['percent'])
        )

        if not self.args.gui:
            if self.args.verbose:
                sys.stdout.write(
                    '%3s:%3d %3s:%3d %3s:%3s ' % (
                        "AMB",round(self.step1.data['ambient'][-1], 0),
                        "SCR", round(self.step1.data['screen'][-1], 0),
                        "COR", str(round(self.step1.data['correction'][-1], 1))
                    )
                )
            sys.stdout.write(
                '%3s:%3d%1s | %3s:%2d %3s:%5.2f%1s %1s:%3d %s %s \r'
                % (
                    "PCT", round(self.step1.data['percent'][-1], 0), "%",
                    "STP", self.step1.data['step'][-1],
                    "AVG", round(self.ValuesAverage,2), "%",
                    "N", len(self.step1.data['percent']),
                    "⚷" if self.lock.lock == True else " ",
                    "⌚" if self.args.logdata == True else " ",
                )
            )
        sys.stdout.flush()
        self.lock.check()

    '''Initializes all iterated classes and starts main loop: gets everything
    needed, computates/executes and print the result according to the verbosity
    level specified
    '''
    def main(self):
        self.mainOp()
        while True:
            self.exeloop()
            if self.drowsiness() is True:
                break
        self.mainEd()


class _locker():

    lock = None
    timestamp = None
    duration = None # lock duration (in sec)

    def __init__(self):
        self.duration = 45

    def expireTime(self):
        try: return self.timestamp - time.time() + self.duration
        except: return None

    def check(self):
        if self.lock is True:
            if self.expireTime() <= 0: self.release()

    def put(self):
        self.lock = True
        self.timestamp = time.time()

    def release(self):
        self.lock = False
        self.timestamp = None