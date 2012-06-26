# -*- coding: utf-8 -*-
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
import sys
from time import time, sleep
import threading

from calise.capture import imaging
from calise.system import execution


class ExecThread(threading.Thread):

    def __init__(self,args):
        global arguments
        arguments = args
        threading.Thread.__init__(self)
        self.func = _MainLoop()

    def run(self):
        self.func.main()


class _MainLoop():

    def __init__(self):
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
        self.ExpPath = arguments.logpath # data export path


    '''checks how much time passed from loop start and sleeps so that the
    entire cycle duration is 'arguments.gap', if that is not possible
    (time passed > arguments.gap), doesn't sleeps.
    Also checks if there are signals waiting to be processed
    '''
    def drowsiness(self):
        for x in range(
            int(round((arguments.gap + self.timeref - time()) / 0.01, 0))
        ):
            # QUIT
            if self.sig == 'quit':
                return True
            # PAUSE / RESUME
            elif self.sig == 'pause':
                self.step0.stop_cam()
                if not arguments.verbosity:
                    sys.stdout.write('\n  =====  PAUSE  =====  \r')
                    sys.stdout.flush()
                while self.sig is not 'resume':
                    if self.sig == 'quit': return True
                    elif self.sig == 'export': WriteLog(); self.sig='pause'
                    sleep(0.01)
                if self.sig is not 'quit': self.step0.set_cam()
            # EXPORT
            elif self.sig == 'export':
                self.WriteLog()
                self.sig = ''
            else:
                sleep(0.01)
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

    '''Initializes all iterated classes and starts main loop: gets everything
    needed, computates/executes and print the result according to the verbosity
    level specified
    '''
    def main(self):
        self.step0 = imaging()
        self.step1 = execution(
            arguments.steps,
            arguments.bkofs,
            arguments.invert,
            arguments.ofs,
            arguments.delta,
            pos = arguments.path,
        )
        self.lock = _locker()
        self.basetime = time() - self.sct
        while True:
            self.timeref = time() # start time of the loop
            self.step0.cam_get(arguments.cam)
            if (
                ( arguments.screen is True ) and
                ( self.basetime + self.sct <= time() ) and
                ( os.getenv('DISPLAY') is not None )
            ):
                self.step0.scr_get()
                self.basetime = time()
            elif arguments.screen is None:
                self.step0.scr = 160
            self.step1.elaborate(self.step0.amb,self.step0.scr)
            if (
                ( arguments.auto ) and
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
            self.step1.PopDataValues(arguments.avg)
            if arguments.logdata:
                for val in self.step1.data:
                    self.step1.history[val].append( self.step1.data[val][-1] )

            self.ValuesAverage = (
                sum(self.step1.data['percent'])/len(self.step1.data['percent'])
            )

            if not arguments.verbosity:
                if arguments.verbose:
                    sys.stdout.write('%3s:%3d %3s:%3d %3s:%3s ' % (
                        "AMB",round(
                            self.step1.data['ambient'][-1] -\
                            self.step1.data['correction'][-1], 0),
                        "SCR", round(
                            self.step1.data['screen'][-1], 0),
                        "COR", str(round(
                            self.step1.data['correction'][-1],1)),))
                sys.stdout.write(
                    '%3s:%3d%1s | %3s:%2d %3s:%5.2f%1s %1s:%3d %s %s \r'
                    % (
                        "PCT", round(self.step1.data['percent'][-1], 0), "%",
                        "STP", self.step1.data['step'][-1],
                        "AVG", round(self.ValuesAverage,2), "%",
                        "N", len(self.step1.data['percent']),
                        "⚷" if self.lock.lock == True else " ",
                        "⌚" if arguments.logdata == True else " ",
                    )
                )
            if arguments.verbosity == 1:
                temp = []
                for item in self.step1.data:
                    temp.append( (item,self.step1.data[item][-1]) )
                temp.append( ('average',self.ValuesAverage) )
                temp.append( ('valnum',len(self.step1.data['ambient'])) )
                lockTime = self.lock.expireTime()
                if lockTime < 0: lockTime = _('None')
                temp.append( ('lock',lockTime) )
                temp.append( ('rec',arguments.logdata) )
                print(temp)
            sys.stdout.flush()

            self.lock.check()
            if self.drowsiness() is True: break
        self.step0.stop_cam()


class _locker():

    lock = None
    timestamp = None
    duration = None # lock duration (in sec)

    def __init__(self):
        self.duration = 45

    def expireTime(self):
        try: return self.timestamp - time() + self.duration
        except: return None

    def check(self):
        if self.lock is True:
            if self.expireTime() <= 0: self.release()

    def put(self):
        self.lock = True
        self.timestamp = time()

    def release(self):
        self.lock = False
        self.timestamp = None