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

import sys
import os
import ConfigParser
import threading
import math
import time
from random import random
from subprocess import Popen, PIPE
from xdg.BaseDirectory import save_config_path, load_config_paths

from calise.infos import __LowerName__
from calise import camera
from calise.capture import imaging, processList, sDev
from calise.system import computation
from calise import optionsd


# -- "PURE" FUNCTIONS ---------------------------------------------------------
# Just a bad, hackish function to obtain data from udevadm
# Reads from UDEV's class video4linux specified device following standard
# naming rules... if device name was customized things may go bad
def UdevQuery(interface='/dev/video0'):
    UDevice = {
        'DEVICE': None,
        'KERNEL': None,
        'SUBSYSTEM': None,
        'DRIVER': None,
        'ATTR': {},
    }
    txt = []
    if os.path.islink(interface):
        link = os.readlink(interface)
        if link.startswith('/'):
            interface = link
        else:
            interface = '%s%s' % (interface[:5], link)
    itf = interface[5:]
    pcs = Popen([
            'udevadm', 'info', '-a', '-p',
            '%s%s' % ('/sys/class/video4linux/',
            itf)], stdout=PIPE, stderr=PIPE)
    pcl = pcs.communicate()
    for item in pcl[0].split('\n\n'):
        if item.count(itf) > 0:
            for line in item.splitlines():
                if line.startswith('    '):
                    txt.append(line.lstrip('    '))
                elif line.startswith('  '):
                    line = line.lstrip('  looking at device \'').rstrip('\':')
                    UDevice['DEVICE'] = (
                        '/'.join(line.strip().split('\'')[0].split('/')[:-5]))
    for item in UDevice:
        if type(UDevice[item]) == dict:
            for line in txt:
                if line.count('}==') > 0:
                    voice = line.split('==')[0].\
                        lstrip(item + '{').rstrip('}').strip()
                    UDevice[item][voice] = line.split('==')[1].\
                        strip('\"').strip()
        else:
            for line in txt:
                if line.startswith(item):
                    UDevice[item] = line.split('==')[1].strip('\"').strip()
    return UDevice


# Searches for either given camera, brightness-path or coordinates in main
# profiles; only returns first profile found
# TODO: Search every valid profile found in config paths and return a list of
#       profiles, ordered from higher to lower level
def searchExisting(camera=None, bfile=None, coordinates=None):
    ret = None
    config = ConfigParser.RawConfigParser()
    if camera:
        camera = UdevQuery(camera)['DEVICE']
    searchPaths = optionsd.get_path()
    # search profiles for given settings, when found, break
    for path in searchPaths:
        if os.path.isfile(path):
            config.read(path)
            if camera and config.has_option('Udev', 'device'):
                if config.get('Udev', 'device') == camera:
                    ret = path
            elif bfile and config.has_option('Backlight', 'path'):
                if config.get('Backlight', 'path') == bfile:
                    ret = path
            elif (
                coordinates and (
                config.has_option('Daemon', 'latitude') and
                config.has_option('Daemon', 'longitude')
                ) or (
                config.has_option('Service', 'latitude') and
                config.has_option('Service', 'longitude')
                )):
                ret = path
        if ret:
            break
    return ret


class cameras():
    ''' Camera-list related class

    Get camera list from camera module, remove linked devices and fill a
    dictionary with UDEV informations on every not-linked cam in list

    NOTE: this class uses camera module *directly* but doesn't init/start the
          camera
    '''
    def __init__(self):
        self.camPaths = camera.listDevices()
        self.devices = {}

    # reads PyGame camera list and removes linked duplicates
    def rmLinked(self):
        for i in range(len(self.camPaths)):
            cp = self.camPaths[i]
            if os.path.islink(cp):
                link = os.readlink(cp)
                if link.startswith('/'):
                    self.camPaths[i] = link
                else:
                    self.camPaths[i] = (
                        '%s%s' % (cp.replace(cp.split('/')[-1], ""), link))
        self.camPaths.sort()
        last = self.camPaths[-1]
        for i in range(len(self.camPaths) - 2, -1, -1):
            if last == self.camPaths[i]:
                del self.camPaths[i]
            else:
                last = self.camPaths[i]

    # calls UdevQuery on camera list to fill "devices" dictionary
    def putDeviceInfo(self):
        for item in self.camPaths:
            self.devices[item] = UdevQuery(item)


# A Thread that starts taking frames from camera and does all needed
# operations to get a value average until okToStp var is externally set
# to True.
class calCapture (threading.Thread):

    def __init__(self, path, bfile, steps, bkofs, invert):
        self.cap = imaging()
        self.com = computation()
        self.path = path
        self.data = []
        self.bfile = bfile
        self.steps = steps
        self.bkofs = bkofs
        self.invert = invert
        self.partial = 0
        threading.Thread.__init__(self)

    # stop capture session through imaging.stop flag
    def okToStop(self):
        self.cap.stop = True

    def adjust_scale(self, cur=0):
        den = 100.00 / self.steps
        # set_flt needs a step value on the scale 0 < 9, so, if there's a
        # different scale/offset, it has to be reduced to a 0 < 9 one.
        if self.invert:
            return (self.steps - 1 - (cur - self.bkofs)) * (den / 10.0)
        else:
            return (cur - self.bkofs) * (den / 10.0)

    # Takes a 255based screen brightness value and corrects all data indexes
    # from last correction (from 0 if the first one). Actually replaces a
    # similar code sequence that was processed in "run" function.
    def adjustValues(self, scr):
        idxTot = len(self.data)
        for idx in range(self.partial, idxTot):
            if os.getenv('DISPLAY') is None:
                break
            if scr > 0:
                dstep = self.adjust_scale(
                    self.com.get_values('step', self.bfile))
                self.com.correction(self.data[idx], scr, dstep)
                self.data[idx] -= self.com.cor
        self.partial = idxTot

    def run(self):
        ''' Thread loop function

        After initializing/starting the device, through function getFrameBri
        get a list of all values processed.
        Since getFrameBri can have being run for a long time, only values old
        not more than 5 seconds (more or less, read below) are kept.

        NOTE: since cameras can only take a certain amount of fps, there can
              be a slight error
        '''
        self.cap.initializeCamera(path=self.path)
        self.cap.startCapture()
        startTime = time.time()
        defInt = 2/30.0
        self.data = self.cap.getFrameBri(interval=defInt, loop=True, keep=True)
        del self.data[:-(int(5 / defInt))]
        self.data = processList(self.data)
        self.average = sum(self.data) / len(self.data)
        self.dev = sDev(self.data, average=self.average)
        self.cap.stopCapture()
        self.cap.freeCameraObj()


# tries to write "step number" step in "sys brightness file" bfile. If not able
# to, raises IOError.
def writeStep(step, bfile):
    with open(bfile, 'w') as fp:
        fp.write(str(step) + "\n")


def brFileWriteErr(err, bfile):
    import errno
    if err.errno == errno.EACCES:
        sys.stderr.write(
            "\nIOError: [Errno %d] Permission denied: "
            "'%s'\nPlease set write permission for "
            "current user on that file\n" % (err.errno, bfile))
        sys.exit(1)
    else:
        raise


def dec_convert(dec):
    g = math.floor(dec)
    p = math.floor((dec - g) * 60.0)
    s = round(((dec - g) * 60.0 - p) * 60.0, 0)
    return g, p, s


# -- "NON PURE" FUNCTIONS -----------------------------------------------------
def query_yes_no(question, default="yes"):
    '''Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is one of "yes" or "no".
    '''
    valid = {
        _("yes"): "yes", _("y"): "yes",
        _("no"): "no", _("n"): "no"
    }
    if default is None:
        prompt = " [" + _('y') + "/" + _('n') + "] "
    elif default == "yes":
        prompt = " [" + _('Y') + "/" + _('n') + "] "
    elif default == "no":
        prompt = " [" + _('y') + "/" + _('N') + "] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)
    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return default
        elif choice in valid.keys():
            return valid[choice]
        else:
            sys.stdout.write(
                _("Please respond with 'yes' or 'no' (or 'y' or 'n')") + ".\n")


class CliCalibration():

    """ Wizard-style configuration
    Every "passage" has a short introduction that describes what does it do,
    then there's the function and newly generated values (from self or simply
    returned) are printed after a ">>> " string.
    """
    def __init__(self, configpath=None, brPath=None):

        # Profile name passage
        print("Step 1 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        print(_(
            "This passage gets a valid profile name to be stored as config "
            "file\'s filename."))
        configname = self.ConfigFilenamePassage(configpath)
        print(">>> " + _("profile name: %s") % configname)
        print(">>> " + _("profile path: %s") % self.configpath)
        print("\n")

        # Sysfs backlight path passage
        print("Step 2 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        print(_(
            "This passage lists all available sysfs backlight directories "
            "and, if more than one, asks wich has to be used."))
        self.BacklightPathPassage(brPath)
        print(">>> " + _("sysfs backlight path: %s") % self.bfile)
        print("\n")

        # Backlight steps passage
        print("Step 3 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        print(_(
            "This passage obtains available backlight steps with selected "
            "sysfs backlight path and displays them ordered from lower to "
            "higher backlight level."))
        self.BacklightPassage()
        print(">>> " + _("backlight steps: %s") % ", ".join(
            [str(x) for x in range(self.bkofs, self.steps + self.bkofs)]))
        print("\n")

        # Geo-coordinates passage
        print("Step 4 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        print(_(
            "This passage asks for latitude and longitude; these are needed "
            "for service execution. The service has a lot of spatio-temporal "
            "optimization to reduce power and cpu usage, based on these "
            "coordinates (thanks to the grat \"ephem\" module)."))
        lat, lon = self.geoLocate()
        print(">>> " + _("Latitude, Longitude: %.6f, %.6f") % (lat, lon))
        print("\n")

        # Camera passage
        print("Step 5 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        print(_(
            "This passage lists all available cameras on this machine and, "
            "if more than one, asks wich camera has to be used."))
        self.CameraPassage()
        sys.stdout.write(">>> " + _("camera: %s") % str(self.camera))
        try:
            print(" (%s)" % self.udevice["ATTR"]["name"])
        except KeyError:
            print("")
        print("\n")

        # Camera white balance offset passage
        print("Step 6 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        print(_(
            "This passage lets the program be aware of the lower lightness "
            "that can be registered by the camera to contrast its white "
            "balance feature."))
        self.OffsetPassage()
        print(
            ">>> " + _("Average camera offset: %.1f") % round(self.offset, 1))
        print("\n")

        # Brightness/Backlight user preferrend scale conversion
        print("Step 7 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        print(_(
            "This passage starts an interactive \"capture\" session where "
            "you'll be asked to select the best backlight step for that very "
            "moment. And of course \"the more the brightness, the more the "
            "precision\"."))
        pct, cbs = self.ValuePassage()
        print(">>> " + _(
            "percentage: %.2f%% and backlight step: %d for current "
            "ambient brightness.") % (pct, cbs))
        print(">>> " + _("Conversion scale delta: %.3f") % self.delta)
        print("\n")
        self.WritePassage()

    # Obtains a valid config filename
    def ConfigFilenamePassage(self, configname=None):
        if configname is None:
            while True:
                configname = raw_input(
                    _("Enter a name for the new profile") + ": ")
                if (
                    configname != configname + os.path.dirname(configname) or
                    configname == ""):
                    print(_("Please retry and enter a valid name."))
                    print(_(
                        "Since it\'ll be a filename, chars not supported by "
                        "your os will raise an error") + "\n")
                    time.sleep(1.5)
                elif os.listdir(
                    save_config_path(__LowerName__)).\
                    count(configname + ".conf") > 0:
                    dummy = query_yes_no(
                        _("The selected profile already exists, overwrite?"),
                        'no')
                    if dummy == 'yes':
                        break
                else:
                    break
                sys.stdout.write("\n")
        self.configpath = os.path.join(
            save_config_path(__LowerName__), configname + '.conf')
        return configname

    # Gets sys/class/backlight infos
    # CAN SKIP = YES (profile already exists)
    def BacklightPathPassage(self, brPath=None):
        if not brPath:
            bfile_list = []
            scb = os.path.join("/", "sys", "class", "backlight")
            #step0 = computation()
            for bd in os.listdir(scb):
                brPath = os.path.join(str(scb), str(bd), 'brightness')
                if os.path.isfile(brPath):
                    #step0.get_values('all', brPath)
                    bfile_list.append(brPath)
        else:
            self.bfile = brPath
            return self.bfile
        if len(bfile_list) == 1:
            self.bfile = bfile_list[0]
            return self.bfile
        # If cannot be skipped
        if len(bfile_list) == 0:
            sys.stderr.write(_(
                "\nYour system does not appear to have controllable "
                "backlight\n"))
            sys.exit(1)
        print("\n" + "\n".join(
            ["%d: %s" % (x + 1, bfile_list[x]) for x in range(len(bfile_list))]
        ))
        print(_(
            "\nNOTE: To be sure you pick the right one, try to change "
            "manually the backlight level and check with a simple cat "
            "command (eg. \"cat %s\") wich one of the path displayed changes "
            "its value when changing backlight level.") % bfile_list[0])
        while True:
            bfile_idx = raw_input(_(
                "Choose one of the path listed above (None=%d): ") % 1)
            try:
                if bfile_idx == '':
                    self.bfile = bfile_list[0]
                    break
                elif int(bfile_idx) <= len(bfile_list) and int(bfile_idx) > 0:
                    self.bfile = bfile_list[int(bfile_idx) - 1]
                    break
                else:
                    print(_(
                        "Please retry and enter an integer in the "
                        "valid range 1-%d!") % len(bfile_list))
            except ValueError, err:
                print(_("Please retry and enter an integer!"))
            sys.stdout.write("\n")
        return self.bfile

    # Gets sys/class/backlight infos
    # CAN SKIP = YES (profile already exists)
    def BacklightPassage(self):
        # list cointaining every /sys/class/backlight/*/brightness path in the
        # system, then only one element of the list will be taken changing
        # self.bfile type from list to string
        bkConf = searchExisting(bfile=self.bfile)
        if bkConf:
            config = ConfigParser.RawConfigParser()
            config.read(bkConf)
            self.steps = config.getint('Backlight', 'steps')
            self.bkofs = config.getint('Backlight', 'offset')
            self.invert = config.getboolean('Backlight', 'invert')
        else:
            step0 = computation()
            raw_input(_("Set the backlight to the minimum then press enter"))
            step0.get_values('all', self.bfile)
            bkofs = step0.bkstp
            steps = step0.bkmax
            if steps < bkofs:
                invert = True
                steps, bkofs = bkofs, steps
                steps = steps + 1 - bkofs
            else:
                invert = False
                steps = steps + 1 - bkofs
            self.steps = steps
            self.bkofs = bkofs
            self.invert = invert

    # Asks for geolocation coordinates
    def geoLocate(self):
        geoConf = searchExisting(coordinates=True)
        if geoConf:
            config = ConfigParser.RawConfigParser()
            config.read(geoConf)
            if config.has_option('Daemon', 'latitude'):
                lat = config.getfloat('Daemon', 'latitude')
                lon = config.getfloat('Daemon', 'longitude')
            elif config.has_option('Service', 'latitude'):
                lat = config.getfloat('Service', 'latitude')
                lon = config.getfloat('Service', 'longitude')
            dummy = query_yes_no(_(
                "\nThe program has found these coordinates (%s, %s) in an "
                "existing profile, would you like to use these values also "
                "for that one? ") % (lat, lon), "yes")
            if dummy == "yes":
                self.lat, self.lon = lat, lon
                return lat, lon
        print(_(
            "If you don\'t know where to find latitude/longitude, "
            "http://www.earthtools.org/ is a good place to start from."))
        print(_(
            "\nNOTE: N and E values have [+], S and W have instead [-]."))
        eg_lat = (random() * .85) * 100
        eg_lon = (random() * 1.8) * 100
        eg_dlat = dec_convert(eg_lat)
        eg_dlon = dec_convert(eg_lon)
        print("  eg.1: %.6f,%.6f   for %d°%02d\'%02d\"N, %d°%02d\'%02d\"E" % (
            eg_lat, eg_lon,
            eg_dlat[0], eg_dlat[1], eg_dlat[2],
            eg_dlon[0], eg_dlon[1], eg_dlon[2],
        ))
        print("  eg.2: %.6f,%.6f  for %d°%02d\'%02d\"N, %d°%02d\'%02d\"W" % (
            eg_lat, -eg_lon,
            eg_dlat[0], eg_dlat[1], eg_dlat[2],
            eg_dlon[0], eg_dlon[1], eg_dlon[2],
        ))
        print("  eg.3: %.6f,%.6f for %d°%02d\'%02d\"S, %d°%02d\'%02d\"W" % (
            -eg_lat, -eg_lon,
            eg_dlat[0], eg_dlat[1], eg_dlat[2],
            eg_dlon[0], eg_dlon[1], eg_dlon[2],
        ))
        while True:
            line = raw_input(_(
                "Please enter your latitude and longitude as comma separated "
                "float degrees (take a look a the examples above): "))
            line = line.replace(', ', ',').split(',')
            try:
                lat = float(line[0])
                lon = float(line[1])
            except (ValueError, IndexError):
                lat = 1000.0
                lon = 1000.0
            if abs(lat) > 85.0 or abs(lon) > 180.0 or len(line) > 2:
                print(_(
                    "Either latitude or longitude values are wrong, please "
                    "check and retry.\n"))
            else:
                break
        self.lat, self.lon = lat, lon
        return lat, lon

    # Gets wich camera has to be used
    # CAN SKIP = YES (system has got only one camera)
    def CameraPassage(self):
        devs = cameras()
        devs.rmLinked()
        devs.putDeviceInfo()
        if len(devs.devices) > 1:
            try:
                print "\n".join(
                    ["%d: %s (%s)" % (
                        x + 1, devs.camPaths[x],
                        devs.devices[devs.camPaths[x]]['ATTR']['name']
                        ) for x in range(len(devs.camPaths))])
            except KeyError:
                print "\n".join(
                    ["%d: %s" % (
                        x + 1, devs.camPaths[x]
                        ) for x in range(len(devs.camPaths))])
            while True:
                webcam = raw_input(
                    _("Choose one of cams listed above (None=%s): ") %
                        devs.camPaths[0])
                try:
                    if webcam == '':
                        webcam = devs.camPaths[0]
                        break
                    elif int(webcam) <= len(devs.camPaths) and int(webcam) > 0:
                        webcam = devs.camPaths[int(webcam) - 1]
                        break
                    else:
                        print(_(
                                "Please retry and enter an integer in the "
                                "valid range 1-%d!") % len(devs.camPaths))
                except ValueError, err:
                    print(_("Please retry and enter an integer!"))
                sys.stdout.write("\n")
        else:
            webcam = devs.camPaths[0]
        self.camera = webcam
        self.udevice = devs.devices[webcam]

    '''This passage obtains an average of the brightness offset generated by
    camera's white-balance feature
    '''
    # CAN SKIP = YES (profile already exists)
    def OffsetPassage(self):
        camConf = searchExisting(camera=self.camera)
        if camConf:
            config = ConfigParser.RawConfigParser()
            config.read(camConf)
            self.offset = config.getfloat('Camera', 'offset')
        else:
            raw_input(_('Cover the webcam and then press enter'))
            print(
                _('Now calibrating') + ", " +
                _("do not uncover the webcam") + "...")
            valThread = calCapture(
                self.camera, self.bfile, self.steps, self.bkofs, self.invert)
            startTime = time.time()
            valThread.start()
            while time.time() - startTime < 4:
                time.sleep(.1)
            valThread.okToStop()
            valThread.join(10)
            self.offset = valThread.average
        return self.offset

    # CAN SKIP = NO
    def ValuePassage(self):
        raw_input(_('Uncover the camera and press enter when ready to start'))
        sys.stdout.write(_('Now calibrating') + '... ')
        sys.stdout.flush()
        valThread = calCapture(
                self.camera, self.bfile, self.steps, self.bkofs, self.invert)
        startTime = time.time()
        valThread.start()
        cap = imaging()
        while time.time() - startTime < 4:
            time.sleep(.1)
        print(_('Capture thread started.'))
        time.sleep(0.75)
        while True:
            print('')
            p = raw_input(_(
                'Choose a value for the current ambient brightness, consider '
                'that the more brightness there is, the more precise will the '
                'scale of the program be, supported values are backlight '
                'steps or percents (eg. 5 or 56%): ')
            )
            try:
                if str(p)[-1] == '%':
                    percentage = float(str(p)[:-1])
                    curStep = int(round(
                        self.bkofs - 1 + percentage / (100.0 / self.steps), 0
                    ))
                    if curStep >= self.steps:
                        curStep = self.steps - 1
                    cap.getScreenBri()
                    valThread.adjustValues(cap.scr)
                    try:
                        writeStep(curStep, self.bfile)
                    except IOError as err:
                        valThread.okToStop()
                        valThread.join(10)
                        brFileWriteErr(err, self.bfile)
                    dummy = query_yes_no(_(
                            "Choosen percentage value roughly equals to the "
                            "%dth backlight step, would you like to use that "
                            "value?") % (curStep), "yes")
                    if dummy == "yes":
                        break
                elif (
                    (int(p) >= self.bkofs) and
                    (int(p) - self.bkofs < self.steps)):
                    curStep = int(p)
                    percentage = (
                        (curStep + 1 - self.bkofs) *
                        (100.0 / self.steps))
                    cap.getScreenBri()
                    valThread.adjustValues(cap.scr)
                    try:
                        writeStep(curStep, self.bfile)
                    except IOError as err:
                        valThread.okToStop()
                        valThread.join(10)
                        brFileWriteErr(err, self.bfile)
                    dummy = query_yes_no(
                        _(
                            'Choosen backlight step value roughly equals to '
                            '%.2f%% of ambient brightness, would you like to '
                            'use that value?'
                        ) % (percentage), 'yes')
                    if dummy == 'yes':
                        break
                else:
                    print(_(
                        'Please retry and enter a value according to the '
                        'rules above'
                    ))
                    time.sleep(1.5)
            except ValueError:
                print(_(
                    "Please retry and enter a value according to the rules "
                    "above"
                ))
                time.sleep(1.5)
            print("")
        valThread.okToStop()
        valThread.join(10)
        self.delta = (valThread.average - self.offset) / (percentage ** 1.372)
        return percentage, curStep

    def WritePassage(self):
        print(_('Making a config file with the choosen settings...'))
        config = ConfigParser.RawConfigParser()
        config.add_section('Camera')
        config.set('Camera', 'camera', str(self.camera))
        config.set('Camera', 'delta', str(self.delta))
        config.set('Camera', 'offset', str(self.offset))
        config.add_section('Backlight')
        config.set('Backlight', 'path', str(self.bfile))
        config.set('Backlight', 'steps', str(self.steps))
        config.set('Backlight', 'offset', str(self.bkofs))
        config.set('Backlight', 'invert', str(self.invert))
        config.add_section('Service')
        config.set('Service', 'latitude', self.lat)
        config.set('Service', 'longitude', self.lon)
        config.add_section('Udev')
        config.set('Udev', 'kernel', self.udevice['KERNEL'])
        config.set('Udev', 'device', self.udevice['DEVICE'])
        config.set('Udev', 'subsystem', self.udevice['SUBSYSTEM'])
        config.set('Udev', 'driver', self.udevice['DRIVER'])
        config.set('Udev', 'attr', ';'.join(
                ['%s=%s' % (x, self.udevice['ATTR'][x])
                for x in self.udevice['ATTR']]))
        try:
            with open(self.configpath, 'wb') as configfile:
                config.write(configfile)
        except IOError, err:
            raise
        print('>>> ' + _('config file saved as: %s') % self.configpath)
        if os.path.basename(self.configpath) != 'default.conf':
            print ""
            print(_(
                "To use the new profile add \"--profile %s\" to the "
                "switches") % (os.path.basename(self.configpath)[:-5]))
        if (
            not os.path.isfile(os.path.join('/', 'etc', 'calise.conf')) and
            os.path.basename(self.configpath) == 'default.conf'):
            print ""
            print(_(
                "You may want to use this profile as system-wide one; "
                "to achieve that copy \"%s\" to \"%s\""
                % (self.configpath, os.path.join('/', 'etc', 'calise.conf'))))
