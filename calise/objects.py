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

import time
import datetime
import logging

from calise.system import computation
from calise.capture import imaging, processList
from calise.sun import getSun, get_daytime_mul, get_geo
from calise.infos import __LowerName__


caliseCompute = computation()


class objects():

    def __init__(self, settings):
        self.logger = logging.getLogger(".".join([__LowerName__, 'objects']))
        self.arguments = settings
        self.oldies = []
        self.resetComers()
        self.wts = None  # weather timestamp
        self.gts = None  # geoip timestamp
        self.capture = imaging()
        self.capture.initializeCamera(self.arguments['cam'])

    def dumpValues(self, allv=False):
        if allv:
            return self.oldies
        else:
            return self.oldies[-1]

    def resetComers(self):
        self.newcomers = {
            "amb": None,  # ambient brightness
            "scr": None,  # screen brightness
            "pct": None,  # (corrected) brightness percentage
            "cbs": None,  # current backlight step
            "sbs": None,  # suggested backlight step
            "cts": None,  # capture timestamp (epoch)
            "css": None,  # sun state: either dawn, day, sunset or night
            "nss": None,  # seconds before next sun state
            "slp": None,  # thread sleeptime
            }

    # Takes a list with a certain amount of %newcomers% keys and optimize
    # resource usage when grabbing every information.
    # Returns a dictionary (with %newcomers% keys)
    def grab_infos(self, info_list):
        if type(info_list) is not list:
            info_list = [info_list]
        info_dict = {}
        if info_list.count('cts'):
            self.getCts()
            info_dict['cts'] = self.newcomers['cts']
        if (
            info_list.count('css') or
            info_list.count('nss') or
            info_list.count('slp')):
            self.executer(False)
            if info_list.count('css'):
                info_dict['css'] = self.newcomers['css']
            if info_list.count('nss'):
                info_dict['nss'] = self.newcomers['nss']
            if info_list.count('nss'):
                info_dict['slp'] = self.newcomers['slp']
        if info_list.count('sbs'):
            self.getSbs()
            for info in info_list:
                info_dict[info] = self.newcomers[info]
        elif info_list.count('pct'):
            self.getPct()
            for info in info_list:
                info_dict[info] = self.newcomers[info]
        else:
            for info in info_list:
                if info == 'cbs':
                    info_dict[info] = self.getCbs()
                if info == 'scr':
                    info_dict[info] = self.getScr()
                if info == 'amb':
                    info_dict[info] = self.getAmb()
        return info_dict

    # obtain timestamp
    def getCts(self):
        self.newcomers['cts'] = time.time()
        return self.newcomers['cts']

    # simple function to obtain ambient brightness (new or existing value)
    def getAmb(self):
        if not self.newcomers['cts']:
            self.getCts()
        self.capture.startCapture()
        camValues = self.capture.getFrameBri(
            self.arguments['capint'], self.arguments['capnum'])
        self.capture.stopCapture()
        camValues = processList(camValues)
        self.logger.debug(
            "Processed values: %s" % ', '.join(["%d" % x for x in camValues]))
        self.newcomers['amb'] = sum(camValues) / float(len(camValues))
        return self.newcomers['amb']

    # simple function to obtain screen brightness (new or existing value)
    def getScr(self):
        if not self.newcomers['cts']:
            self.getCts()
        self.capture.getScreenBri()
        self.newcomers['scr'] = self.capture.scr
        return self.newcomers['scr']

    # obtains brightness percentage value, corrected if needed (by the amount
    # of brightness coming from the screen)
    def getPct(self):
        self.getAmb()
        self.getScr()
        self.getCbs()
        caliseCompute.percentage(
            self.newcomers['amb'],
            self.arguments['offset'], self.arguments['delta'],
            self.newcomers['scr'],
            self.adjustScale(self.newcomers['cbs']))
        self.newcomers['pct'] = caliseCompute.pct
        return self.newcomers['pct']

    # simple function to obtain current backlight step (new or existing value)
    def getCbs(self):
        caliseCompute.get_values('step', self.arguments['path'])
        self.newcomers['cbs'] = caliseCompute.bkstp
        self.arguments['bfile'] = caliseCompute.bfile
        return self.newcomers['cbs']

    # obtain suggested backlight step. This function need every value of
    # %newcomers% dictionary
    def getSbs(self):
        steps = self.arguments['steps']
        bkofs = self.arguments['bkofs']
        self.getPct()
        stp = int(self.newcomers['pct'] / (100.0 / steps) - .5 + bkofs)
        if self.arguments['invert']:
            stp = steps - 1 + bkofs - stp + bkofs
        # out-of-bounds control...
        if stp > steps - 1 + bkofs:
            stp = steps - 1 + bkofs
        elif stp < bkofs:
            stp = bkofs
        self.newcomers['sbs'] = stp
        return self.newcomers['sbs']

    # complementary to getPct function
    def adjustScale(self, cur):
        steps = self.arguments['steps']
        bkofs = self.arguments['bkofs']
        den = 100.00 / steps
        if self.arguments['invert']:
            return (steps - 1 - (cur - bkofs)) * (den / 10.0)
        else:
            return (cur - bkofs) * (den / 10.0)

    """ Backlight-step change writer
    Checks for read permission and if so writes current backlight step on sys
    brightness file (the one selected throug computation)
    If increasing is set either to False or True and if previous backlight
    step was lower/higher, writeStep will return False (no change)
    """
    def writeStep(self, increasing=None, standalone=False):
        if standalone:
            self.getCts()
        self.getSbs()
        bfile = self.arguments['bfile']
        if self.arguments['invert']:
            increasing = not increasing
        refer = int(self.newcomers['sbs']) - int(self.newcomers['cbs'])
        if ((
            refer > 0 and increasing is True) or (    # dawn condition
            refer < 0 and increasing is False) or (   # sunset condition
            abs(refer) > 1) or (                      # room light lit/shut
            abs(refer) > 0 and increasing is None)):  # normal statement
            try:
                fp = open(bfile, 'w')
            except IOError as err:
                import errno
                if err.errno == errno.EACCES:
                    self.logger.error(
                        "IOError: [Errno %d] Permission denied: \'%s\'\n"
                        "Please set write permission for current user\n"
                        % (err.errno, bfile))
                    return 2
            else:
                with fp:
                    fp.write(str(self.newcomers['sbs']) + "\n")
                    self.newcomers['cbs'] = self.newcomers['sbs']
                    return 0
        else:
            return 1

    # get "weather" multiplier, updates only once per hour
    def getWtr(self, cur=None):
        if cur is None:
            cur = time.time()
        if self.wts is None or cur - self.wts > 3600:
            self.wts = time.time()
            mul = get_daytime_mul(
                self.arguments['latitude'], self.arguments['longitude'])
            self.daytime_mul = mul
            return 0
        return 1

    # get geoip informations, updates only once every 30 minutes
    def getGeo(self, cur=None):
        if cur is None:
            cur = time.time()
        if self.gts is None or cur - self.gts > 1800:
            self.gts = time.time()
            geo = get_geo()
            if geo:
                self.arguments['latitude'] = geo['lat']
                self.arguments['longitude'] = geo['lon']
                return 0
            else:
                return 2
        return 1

    def autoWrite(self):
        # assign increasing values (refer to writeStep for further info)
        if self.newcomers['css'] == "dawn":
            inc = True
        elif self.newcomers['css'] == "sunset":
            inc = False
        else:
            inc = None
        # logs writeStep execution
        r = self.writeStep(increasing=None)
        self.logger.debug("Function '%s' returned %d" % ('writeStep', r))
        return 0

    def executer(self, execute=True, ctime=None):
        """ service "core"

        With the help of the getSun function (which use ephem module) in
        calise.sun module, discovers current time of the day and sets sleep
        time before a new capture and increasing/decreasing writeStep args
        accordingly

        """
        if not self.newcomers['cts']:
            self.getCts()
        if ctime is None:
            cur_time = time.time()
        else:
            cur_time = ctime
        capture_time = self.arguments['capnum'] * self.arguments['capint']
        if self.arguments['geoip']:
            self.getGeo()

        if (
            not self.arguments.keys().count('latitude') or
            not self.arguments.keys().count('longitude') or
            self.arguments['latitude'] is None or
            self.arguments['longitude'] is None
        ):
            arbSlpVal = 90.0
            self.logger.warning(
                "Not able to geolocate, setting arbitrary sleeptime value: %d"
                % arbSlpVal)
            self.newcomers['css'] = None
            self.newcomers['nss'] = None
            self.newcomers['slp'] = arbSlpVal
            if execute:
                self.autoWrite()
            else:
                self.getSbs()
            return arbSlpVal - capture_time + cur_time

        sun = getSun(
            self.arguments['latitude'], self.arguments['longitude'])
        daw = float(sun[0])
        sus = float(sun[1])

        # more or less the seconds that the sun needs to get from min to max
        # backlight step brightness
        daw_tw = int(sun[2])
        sus_tw = int(sun[3])

        # sleeptime between captures
        #
        # if ipotetically during daw_tw/sus_tw the backlight goes from max to
        # min, then there will be a step change every %x% sec, to be more
        # precise I decided to set sleeptime to %x% / 10
        #
        # EDIT: machines with more than 10000 backlight steps 'blowed-up' with
        #       previous formula, percentage will work better there
        #
        daw_sl = daw_tw / 100.0
        sus_sl = sus_tw / 100.0

        # happens on artic regions, where the sun is always above the horizon
        if daw is True and sus is False:
            self.newcomers['css'] = "day"
            self.newcomers['nss'] = None
            if self.arguments['weather']:
                self.getWtr(cur_time)
            else:
                self.daytime_mul = 0.6
            sleepTime = self.arguments['dayst'] * self.daytime_mul
            if sleepTime + time.time() > self.newcomers['nss']:
                sleepTime = self.newcomers['nss'] - time.time()
        # happens on artic regions, where the sun never reaches above the
        # horizon
        elif daw is False and sus is True:
            self.newcomers['css'] = "night"
            self.newcomers['nss'] = None
            if self.arguments['nightst'] == 0.0:
                sleepTime = (
                    int(datetime.date.today().strftime("%s")) +
                    86400 - cur_time)
            else:
                sleepTime = self.arguments['nightst']
        # happens on artic regions, where the sun never reaches 15 degrees
        # above the horizon, so, actually, dawn/sunset time equal half each of
        # the time the sun spend above the horizon
        elif sus == daw + daw_tw:
            if cur_time < daw + daw_tw / 2.0:
                self.newcomers['css'] = "dawn"
                sleepTime = daw_sl * self.arguments['dusksm']
            else:
                self.newcomers['css'] = "sunset"
                sleepTime = daw_sl * self.arguments['dusksm']
        # dawn
        elif cur_time > daw and cur_time <= daw + daw_tw:
            self.newcomers['css'] = "dawn"
            self.newcomers['nss'] = daw + daw_tw - cur_time
            sleepTime = daw_sl * self.arguments['dusksm']
        # sunset
        elif cur_time >= sus - sus_tw and cur_time < sus:
            self.newcomers['css'] = "sunset"
            self.newcomers['nss'] = sus - cur_time
            sleepTime = sus_sl * self.arguments['dusksm']
        # night
        elif cur_time > sus or cur_time < daw:
            # if current time is before midnight, ask for next day dawn
            if cur_time > sus:
                tmp = getSun(
                    self.arguments['latitude'], self.arguments['longitude'],
                    cur_time + 24 * 60 * 60)
                daw = float(tmp[0])
            if self.arguments['nightst'] == 0.0:
                sleepTime = daw - cur_time
            else:
                sleepTime = self.arguments['nightst']
            self.newcomers['css'] = "night"
            self.newcomers['nss'] = daw - cur_time
        # day
        else:
            self.newcomers['css'] = "day"
            self.newcomers['nss'] = sus - sus_tw - cur_time
            if self.arguments['weather']:
                self.getWtr(cur_time)
            else:
                self.daytime_mul = 0.6
            sleepTime = self.arguments['dayst'] * self.daytime_mul
            if sleepTime > self.newcomers['nss']:
                sleepTime = self.newcomers['nss']
        # *real* execute
        if execute:
            self.autoWrite()
        else:
            self.getSbs()
        # process output value
        self.newcomers['slp'] = sleepTime
        if sleepTime < capture_time + 1.0:
            return capture_time + 1.0 + cur_time
        else:
            return sleepTime - capture_time + cur_time

    def append_data(self):
        obj = self.newcomers
        self.oldies.append(obj)
