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
import errno
from math import atan, pi
from time import time


class computation():
    ''' Computation-realted tasks

    In this class are set custom equations to obtain:
        - maximum lightness correction
        - effective correction
        - brightness percentage (using user-defined scale)

    There are also backlight directory's functions. All parameters are briefly
    explained below

    '''

    def __init__(self):
        self.scr = None # screen brightness 0 < 255
        self.amb = None # ambient brightness 0 < 255
        self.cor = None # calculated brightness correction
        self.pct = None # calculated brightness percentage

        self.bfile = None # brightness sys file that manages backlight level

        self.bkstp = None # current backlight step
        self.bkmax = None # maximum backlight step
        self.bkpow = None # 0 = power-on, 1 = power-off

    # calculates ambient brightness correction using screen backlight value
    def correction(self, amb=0, scr=0, dstep=0):
        max_cor_mul = (2 * (160 - amb) ** 2) / float((amb + 136) ** 2)
        screen_mul = (scr / 255.0 ) ** 2
        backlight_mul = (1.0 / 5.0) * (dstep / (5.0 / 4.0))
        cor = amb * max_cor_mul * screen_mul * backlight_mul
        if amb > 160:
            cor = 0
        self.cor = cor

    # calculates ambient brightness percentage using user-defined scale
    def percentage(
        self, amb, ofs=0.0, delta=255 / (100 ** (1 / 0.73)), scr=0, dstep=0
    ):
        if (scr == None)|(dstep == None):
            self.cor = 0
            scr = 0
            dsetp = 0
        else:
            self.correction(amb, scr, dstep)
        self.scr = scr
        self.amb = amb
        cor = self.cor
        amb = amb - cor
        if ofs > amb:
            ofs = amb
        self.pct = ((amb - ofs) / delta) ** .73


    def read_backlight(self, ix=0, pt=None):
        ret = None
        af = ['brightness', 'max_brightness', 'bl_power', 'actual_brightness']
        # check inputs
        if not type(ix) in [int, float]:
            ix = 0
        if pt is None and self.bfile:
            pt = self.bfile
        if type(pt) in [str]:
            if os.path.isdir(pt) and os.path.isfile(os.path.join(pt, af[ix])):
                path = pt
            elif os.path.isfile(os.path.join(os.path.dirname(pt), af[ix])):
                path = os.path.dirname(pt)
            else:
                path = None
            if path:
                try:
                    with open(os.path.join(path, af[ix]), 'r') as fp:
                        ret = int(fp.readline())
                except ValueError:
                    sys.stderr.write(
                        "ValueError: choosen \"%s\" file (%s) is not valid\n"
                        % (af[ix], path))
                    raise
                except IOError as err:
                    if err.errno == errno.EACCES:
                        sys.stderr.write(
                            "IOError: [Errno %d] Permission denied: \"%s\"\n"
                            "Please set read permission for current user\n"
                            % (err.errno, path))
                    raise
        if ret is None:
            raise ValueError
        if ix == 0 and not self.bfile:
            self.bfile = os.path.join(path, af[ix])
        return ret

    # choice = step|max|power|all
    def get_values(self, choice='step', path=None):
        ret = None
        if choice == 'step':
            self.bkstp = self.read_backlight(0, path)
            ret = self.bkstp
        elif choice == 'max':
            self.bkmax = self.read_backlight(1, path)
            ret = self.bkmax
        elif choice == 'power':
            self.bkpow = self.read_backlight(2, path)
            ret = self.bkpow
        elif choice == 'actual':
            self.actual = self.read_backlight(3, path)
            ret = self.actual
        elif choice == 'all':
            self.bkstp = self.read_backlight(0, path)
            self.bkstp = self.read_backlight(3, path)
            self.bkmax = self.read_backlight(1, path)
            self.bkpow = self.read_backlight(2, path)
            ret = [self.bkstp, self.bkmax, self.bkpow]
        return ret


'''Execution class
This class obtains a step value out of some vars that must be given manually
'''
class execution():

    steps = None # number of backlight steps
    bkofs = None # first step
    invert = None # False: scale is min > max, True: max > min

    ofs = None # equation offset (user defined, got from calibration)
    delta = None # equation modifier (user defined, got from calibration)
    pos = None # sys backlight device control folder
    tol = None # percentage tolerance for hard drop

    bfile = None # brightness sys file (taken from computation)
    bkstp = None # current backlight step (taken from computation)

    # each dictionary voice contains all previous valid measurements
    data = {
        'timestamp': [],
	'ambient': [],
	'screen': [],
	'correction': [],
	'percent': [],
	'step': [],
	'bkstp': [],
    }
    history = {
        'timestamp': [],
	'ambient': [],
	'screen': [],
	'correction': [],
	'percent': [],
	'step': [],
	'bkstp': [],
    }


    def __init__(
        self,
        steps, bkofs, invert=False,
        ofs=0.0, delta=255/(100**(1/.73)), tol=20,
        pos=None
    ):
        self.steps = steps
        self.bkofs = bkofs
        self.invert = invert
        self.den = 100.00/self.steps
        self.ofs = ofs
        self.delta = delta
        self.tol = tol
        self.pos = pos

    # set_flt needs a step value on the scale 0 < 1, so, if there's a
    # different scale/offset, it has to be reduced to a 0 < 1 one.
    def AdjustScale(self, cur):
        return (cur - self.bkofs + 1) * (1.00 / self.steps)

    # picks brightness percentages, backlight steps and offset and invert, then
    # returns the corresponding backlight step
    def SetStep(self,pct):
        steps = self.steps
        bkofs = self.bkofs
        percs = self.data['percent']
        average = sum(percs)/len(percs)
        stp = int(average / self.den - .5 + bkofs)
        if self.invert:
	    stp = steps - 1 + bkofs - stp + bkofs
        # out-of-bounds control...
        if stp > steps - 1 + bkofs:
	    stp = steps - 1 + bkofs
        elif stp < bkofs:
	    stp = bkofs
        self.data['step'].append(stp)

    # updates value ambient and screen brightness list, can be ommitted if amb
    # is specified in the elaborate() function
    def store(self,amb,scr=None):
        if type(amb) is float or type(amb) is int:
            self.data['ambient'].append(amb)
        else: raise TypeError('amb has to be either float or int')
        if type(scr) is float or type(scr) is int:
	    self.data['screen'].append(scr)
	elif scr is None and len(self.data['screen']) > 0:
	    self.data['screen'].append(self.data['screen'][-1])
	elif scr is None and len(self.data['screen']) == 0:
	    self.data['screen'].append(0)
	else:
	    raise TypeError('scr has to be either float or int (or None)')

    # main function of the class, takes all class vars and returns a backlight
    # step according to them. If there is a difference greater than 20 between
    # two consequent percentages, resets all data
    def elaborate(self,amb=None,scr=None):
        if amb is not None:
	    self.store(amb,scr)
	amb = self.data['ambient'][-1]
	scr = self.data['screen'][-1]
	if len(self.data['timestamp']) < len(self.data['ambient']):
	    self.data['timestamp'].append(round(time(),3))
        comp = computation()
        comp.get_values('step', self.pos)
        comp.percentage(
            amb, self.ofs, self.delta,
            scr, self.AdjustScale(comp.bkstp)
        )
        self.data['correction'].append(comp.cor)
        self.data['percent'].append(comp.pct)
        if len(self.data['percent']) > 1:
            if (
                abs( self.data['percent'][-1] - self.data['percent'][-2] ) >
                self.tol
            ):
	        for bookmark in self.data:
	            if bookmark is 'step':
		        self.data[bookmark] = []
	            else:
		        self.data[bookmark] = [ self.data[bookmark][-1] ]
        self.SetStep(sum(self.data['percent'])/len(self.data['percent']))
        self.data['bkstp'].append(comp.bkstp)
        self.bfile = comp.bfile

    # checks for read permission and writes current backlight step on sys
    # brightness file (the one selected throug computation)
    def WriteStep(self):
        if self.data['step'][-1] != self.data['bkstp'][-1]:
            try:
                fp = open(self.bfile, 'w')
            except IOError as err:
	        if err.errno == errno.EACCES:
	            sys.stderr.write("IOError: [Errno %d] Permission denied: "
	                             "'%s'\nPlease set write permission for "
	                             "current user\n"
			              % (err.errno, self.bfile))
	            quit()
	        raise
            else:
	        with fp:
                    fp.write(str(self.data['step'][-1])+'\n')
                    return True

    # takes the max number of values, checks if data exceeds that value and in
    # that case pops out the first (oldest) value of each voice in the dict
    def PopDataValues(self,n):
        gap = len(self.data['percent']) - n
        if gap >= 0:
	    for x in range(gap+1):
	        for bookmark in self.data:
		    del self.data[bookmark][0]