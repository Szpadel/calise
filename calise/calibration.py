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
from xdg.BaseDirectory import save_config_path, load_config_paths
import textwrap
from select import select

from calise import console

from calise.infos import __LowerName__
from calise import camera
from calise.capture import imaging, processList, sDev
from calise.system import computation
from calise import optionsd
from calise.sun import get_geo


def customWrap(textstring, width=None):
    if width is None:
        width = console.getTerminalSize()[0] - 2
    textstring = textstring.split('\n')
    for idx in range(len(textstring)):
        chadd = ''
        if textstring[idx].endswith(' '):
            chadd = ' '
        textstring[idx] = textwrap.fill(textstring[idx], width) + chadd
    return '\n'.join(textstring)

def fprnt(stringa):
    print customWrap(stringa)


# == "PURE" FUNCTIONS =========================================================
# Get minimum backlight level trying to write values on the device until no
# IOError errno22 is returned
def getMinimumLevel(blpath):
    with open(blpath) as fp:
        currentLevel = int(fp.read())
    startTime = time.time()
    x = 0
    while True:
        try:
            with open(blpath, 'w') as fp:
                fp.write(str(x))
            fprnt(_(
                "This (%d) should be the minimum backlight step possible on "
                "this machine.") % x)
            dummy = query_yes_no(customWrap(_(
                "Are you able to see this message?")),
                default='no', timeout=20)
            with open(blpath, 'w') as fp:
                fp.write(str(currentLevel))
            if dummy == 'yes':
                return x
            else:
                break
        except IOError as err:
            if err.errno == 22:
                x += 1
    return None


def UdevQuery(interface='/dev/video0'):
    UDevice = {
        'KERNEL': None,
        'DEVICE': None,
        'SUBSYSTEM': None,
        'DRIVER': None,
        'ATTR': {},
    }
    # KERNEL
    if os.path.islink(interface):
        link = os.readlink(interface)
        if link.startswith('/'):
            interface = link
        else:
            interface = '%s%s' % (os.path.dirname(interface), link)
    UDevice['KERNEL'] = interface.split('/')[-1]
    #DEVICE
    devicesPath = os.path.join('/sys', 'class', 'video4linux')
    devicePath = os.path.join(devicesPath, UDevice['KERNEL'])
    td = []
    if os.path.islink(devicePath):
        for x in os.readlink(devicePath).split('/'):
            if x != '..':
                td.append(x)
    UDevice['DEVICE'] = os.path.join('/', td[0], td[1], td[2])
    # SUBSYSTEM
    subsystemPath = os.path.join(devicePath, 'subsystem')
    if os.path.islink(subsystemPath):
        UDevice['SUBSYSTEM'] = os.readlink(subsystemPath).split('/')[-1]
    # DRIVER
    UDevice['DRIVER'] = ''
    # ATTR
    for path in os.listdir(devicePath):
        tmpPath = os.path.join(devicePath, path)
        if os.path.isfile(tmpPath) and path != 'dev' and path != 'uevent':
            with open(tmpPath, 'r') as fp:
                UDevice['ATTR'][path] = ' '.join(fp.read().split())
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


def hasControlCapability(path):
    retCode = 0
    capmod = imaging()
    capmod.initializeCamera(path)
    capmod.cameraObj.openPath()
    capmod.adjustCtrls()
    availableCtrls = capmod.ctrls.keys()
    for key in [str(x) for x in [12, 18, 28]]:
        if not availableCtrls.count(key):
            retCode = 1
    capmod.restoreCtrls()
    capmod.cameraObj.closePath()
    capmod.freeCameraObj()
    return retCode

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
        not more than 10 seconds (more or less, read below) are kept.

        NOTE: since cameras can only take a certain amount of fps, there can
              be a slight error
        '''
        self.cap.initializeCamera(path=self.path)
        self.cap.startCapture()
        startTime = time.time()
        defInt = 2/30.0
        self.data = self.cap.getFrameBri(interval=defInt, loop=True, keep=True)
        del self.data[:-(int(10 / defInt))]
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
def query_yes_no(question, default="yes", timeout=None):
    '''Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is one of "yes" or "no".
    '''
    valid = {
        _('yes'): 'yes', _('y'): 'yes',
        _('no'): 'no', _('n'): 'no',
    }
    if default is None:
        prompt = ' [' + _('y') + '/' + _('n') + '] '
    elif default == 'yes':
        prompt = ' [' + _('Y') + '/' + _('n') + '] '
    elif default == 'no':
        prompt = ' [' + _('y') + '/' + _('N') + '] '
    else:
        raise ValueError("invalid default answer: '%s'" % default)
    while True:
        sys.stdout.write(question + prompt)
        sys.stdout.flush()
        if timeout is not None:
            rlist, dull1, dull2 = select([sys.stdin], [], [], timeout)
            if rlist:
                choice = sys.stdin.readline()
                choice = str(''.join(choice.split())).lower()
            else:
                choice = ''
        else:
            choice = raw_input().lower()
        if default is not None and choice == '':
            print default
            return default
        elif choice in valid.keys():
            return valid[choice]
        else:
            print valid.keys()
            sys.stdout.write(_(
                "Please respond with 'yes' or 'no' ('y' or 'n')") + ".\n")


class CliCalibration():

    """ Wizard-style configuration
    Every "passage" has a short introduction that describes what does it do,
    then there's the function and newly generated values (from self or simply
    returned) are printed after a ">>> " string.
    """
    def __init__(self, configpath=None, brPath=None):

        # Profile name passage
        fprnt("Step 1 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage gets a valid profile name to be stored as config "
            "file\'s filename."))
        configname = self.ConfigFilenamePassage(configpath)
        fprnt(">>> " + _("profile name: %s") % str(configname))
        fprnt(">>> " + _("profile path: %s") % str(self.configpath))
        fprnt("\n")

        # Sysfs backlight path passage
        fprnt("Step 2 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage lists all available sysfs backlight directories "
            "and, if more than one, asks wich has to be used."))
        self.BacklightPathPassage(brPath)
        fprnt(">>> " + _("sysfs backlight path: %s") % self.bfile)
        fprnt("\n")

        # Backlight steps passage
        fprnt("Step 3 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage obtains available backlight steps with selected "
            "sysfs backlight path and displays them ordered from lower to "
            "higher backlight level."))
        self.BacklightPassage()
        fprnt(
            ">>> " + _("backlight steps: %s")
            % " -> ".join([str(self.bkofs), str(self.steps + self.bkofs - 1)]))
        fprnt("\n")

        # Geo-coordinates passage
        fprnt("Step 4 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage asks for latitude and longitude; these are really "
            "useful for service execution since it has a lot of spatio-"
            "temporal optimizations (to reduce power and cpu usage), based on "
            "them (thanks to the great \"ephem\" module)."))
        lat, lon = self.geoLocate()
        fprnt(
            ">>> " + _("Latitude, Longitude: %s, %s")
                % ('%.6f' if lat is float else str(lat),
                   '%.6f' if lon is float else str(lon)))
        fprnt("\n")

        # Camera passage
        fprnt("Step 5 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage lists all available cameras on this machine and, "
            "if more than one, asks wich camera has to be used."))
        self.CameraPassage()
        sys.stdout.write(">>> " + _("camera: %s") % str(self.camera))
        try:
            fprnt(" (%s)" % self.udevice["ATTR"]["name"])
        except KeyError:
            fprnt("")
        fprnt("\n")

        # Camera white balance offset passage
        fprnt("Step 6 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage lets the program be aware of the lower lightness "
            "that can be registered by the camera to contrast its white "
            "balance feature."))
        self.OffsetPassage()
        fprnt(
            ">>> " + _("Average camera offset: %.1f") % round(self.offset, 1))
        fprnt("\n")

        # Brightness/Backlight user preferrend scale conversion
        fprnt("Step 7 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage starts an interactive \"capture\" session where "
            "you'll be asked to select the best backlight step for that very "
            "moment. And of course \"the more the brightness, the more the "
            "precision\"."))
        pct, cbs = self.ValuePassage()
        fprnt(">>> " + _(
            "percentage: %.2f%% and backlight step: %d for current "
            "ambient brightness.") % (pct, cbs))
        fprnt(">>> " + _("Conversion scale delta: %.3f") % self.delta)
        fprnt("\n")
        self.WritePassage()

    # Obtains a valid config filename
    def ConfigFilenamePassage(self, configname=None):
        if configname is None and os.getuid() != 0:
            while True:
                configname = raw_input(customWrap(_(
                    "Enter a name for the new profile") + ": "))
                if (
                    configname != configname + os.path.dirname(configname) or
                    configname == ""):
                    fprnt(_("Please retry and enter a valid name."))
                    fprnt(_(
                        "Since it\'ll be a filename, chars not supported by "
                        "your os will raise an error") + "\n")
                    time.sleep(1.5)
                elif os.listdir(
                    save_config_path(__LowerName__)).\
                    count(configname + ".conf") > 0:
                    dummy = query_yes_no(customWrap(_(
                        "Selected profile already exists, overwrite?")), 'no')
                    if dummy == 'yes':
                        break
                else:
                    break
                sys.stdout.write("\n")
            self.configpath = os.path.join(
                save_config_path(__LowerName__), configname + '.conf')
        elif os.getuid() == 0:
            configname = __LowerName__
            configpath = os.path.join('/', 'etc', configname + '.conf')
            if os.path.isfile(configpath):
                dummy = query_yes_no(customWrap(
                    _("Profile already exists, overwrite?")), 'no')
                if dummy == 'no':
                    sys.exit(11)
            self.configpath = configpath
            configname = None
        else:
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
            sys.stderr.write('\n')
            sys.stderr.write(_(
                "Your system does not appear to have controllable "
                "backlight") + '\n')
            sys.exit(1)
        fprnt('\n' + '\n'.join(
            ["%d: %s" % (x + 1, bfile_list[x]) for x in range(len(bfile_list))]
        ))
        print("")
        fprnt(_(
            "NOTE: To be sure you pick the right one, try to change "
            "manually the backlight level and check with a simple cat "
            "command (eg. \"cat %s\") wich one of the path displayed changes "
            "its value when changing backlight level.") % bfile_list[0])
        while True:
            bfile_idx = raw_input(customWrap(_(
                "Choose one of the path listed above (None=%d): ") % 1))
            try:
                if bfile_idx == '':
                    self.bfile = bfile_list[0]
                    break
                elif int(bfile_idx) <= len(bfile_list) and int(bfile_idx) > 0:
                    self.bfile = bfile_list[int(bfile_idx) - 1]
                    break
                else:
                    fprnt(_(
                        "Please retry and enter an integer in the "
                        "valid range 1-%d!") % len(bfile_list))
            except ValueError, err:
                fprnt(_("Please retry and enter an integer!"))
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
            step0.get_values('all', self.bfile)
            fprnt(_(
                "The program will now try to semi-automatically find the "
                "minimum backlight level (before \"power-off\") for this "
                "machine.") + '\n')
            fprnt(_(
                "NOTE: If you'll get a blank screen don't worry and "
                "just wait the default timeout (20 seconds)") + '\n')
            raw_input(customWrap(_("Hit ENTER or RETURN when ready")))
            print("")
            bkofs = getMinimumLevel(self.bfile)
            if bkofs is None:
                raw_input(customWrap(_(
                    "Auto-get minimum backlight step somehow failed, "
                    "trying to obtain the hard-way, set the backlight to "
                    "minimum then hit RETURN or ENTER")))
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
        print("")
        self.lat = None
        self.lon = None
        geo = get_geo()
        if geo is not None:
            lat = geo['lat']
            lon = geo['lon']
        dummy = query_yes_no(customWrap(_(
            "The program has found these coordinates (%s, %s) through geoip "
            "lookup, would you like to use these value?") % (lat, lon)), "yes")
        print("")
        if dummy == "yes":
            self.lat = lat
            self.lon = lon
            return lat, lon
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
            dummy = query_yes_no(customWrap(_(
                "The program has found these coordinates (%s, %s) in an "
                "existing profile, would you like to use these values also "
                "for that one? ") % (lat, lon)), "yes")
            print("")
            if dummy == "yes":
                self.lat = lat
                self.lon = lon
                return lat, lon
        fprnt(_(
            "If you don\'t know where to find latitude/longitude, "
            "http://www.earthtools.org/ is a good place to start from."))
        print("")
        fprnt(_(
            "NOTE: N and E values have [+], S and W have instead [-]."))
        eg_lat = (random() * .85) * 100
        eg_lon = (random() * 1.8) * 100
        eg_dlat = dec_convert(eg_lat)
        eg_dlon = dec_convert(eg_lon)
        fprnt("  eg.1: %.6f,%.6f   for %d°%02d\'%02d\"N, %d°%02d\'%02d\"E" % (
            eg_lat, eg_lon,
            eg_dlat[0], eg_dlat[1], eg_dlat[2],
            eg_dlon[0], eg_dlon[1], eg_dlon[2],
        ))
        fprnt("  eg.2: %.6f,%.6f  for %d°%02d\'%02d\"N, %d°%02d\'%02d\"W" % (
            eg_lat, -eg_lon,
            eg_dlat[0], eg_dlat[1], eg_dlat[2],
            eg_dlon[0], eg_dlon[1], eg_dlon[2],
        ))
        fprnt("  eg.3: %.6f,%.6f for %d°%02d\'%02d\"S, %d°%02d\'%02d\"W" % (
            -eg_lat, -eg_lon,
            eg_dlat[0], eg_dlat[1], eg_dlat[2],
            eg_dlon[0], eg_dlon[1], eg_dlon[2],
        ))
        print("")
        while True:
            line = raw_input(customWrap(_(
                "Please enter your latitude and longitude as comma separated "
                "float degrees (take a look a the examples above), if not "
                "interested in this feature just leave blank: ")))
            if line:
                line = line.replace(', ', ',').split(',')
                try:
                    lat = float(line[0])
                    lon = float(line[1])
                except (ValueError, IndexError):
                    lat = 1000.0
                    lon = 1000.0
                if abs(lat) > 85.0 or abs(lon) > 180.0 or len(line) > 2:
                    fprnt(_(
                        "Either latitude or longitude values are wrong, "
                        "please check and retry.\n"))
                else:
                    self.lat = lat
                    self.lon = lon
                    break
            else:
                break
        # both None if left blank last question
        return self.lat, self.lon

    # Gets wich camera has to be used
    # CAN SKIP = YES (system has got only one camera)
    def CameraPassage(self):
        devs = cameras()
        devs.rmLinked()
        devs.putDeviceInfo()
        if len(devs.devices) > 1:
            try:
                fprnt("\n".join(
                    ["%d: %s (%s)" % (
                        x + 1, devs.camPaths[x],
                        devs.devices[devs.camPaths[x]]['ATTR']['name']
                        ) for x in range(len(devs.camPaths))])
                )
            except KeyError:
                fprnt("\n".join(
                    ["%d: %s" % (
                        x + 1, devs.camPaths[x]
                        ) for x in range(len(devs.camPaths))])
                )
            while True:
                webcam = raw_input(customWrap(
                    _("Choose one of cams listed above (None=%s): ") %
                        devs.camPaths[0]))
                try:
                    if webcam == '':
                        webcam = devs.camPaths[0]
                        break
                    elif int(webcam) <= len(devs.camPaths) and int(webcam) > 0:
                        webcam = devs.camPaths[int(webcam) - 1]
                        break
                    else:
                        fprnt(_(
                                "Please retry and enter an integer in the "
                                "valid range 1-%d!") % len(devs.camPaths))
                except ValueError, err:
                    fprnt(_("Please retry and enter an integer!"))
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
        elif hasControlCapability(self.camera) == 0:
            self.offset = 0.0
        else:
            raw_input(customWrap(_(
                "Cover the webcam and then press ENTER or RETURN")))
            fprnt(
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
        raw_input(customWrap(_(
            "Remove any obstruction from the camera and press ENTER or RETURN "
            "when ready to start")))
        sys.stdout.write(_("Now calibrating") + "... ")
        sys.stdout.flush()
        valThread = calCapture(
                self.camera, self.bfile, self.steps, self.bkofs, self.invert)
        startTime = time.time()
        valThread.start()
        cap = imaging()
        while time.time() - startTime < 4:
            time.sleep(.1)
        fprnt(_("Capture thread started."))
        time.sleep(0.75)
        print("")
        while True:
            tpct = int(round(120 * random(), 0))
            tstp = int(round(self.bkofs - 1 + tpct / (100.0 / self.steps), 0))
            if tstp > self.steps - 1 + self.bkofs:
                tstp = self.steps - 1 + self.bkofs
            elif tstp < self.bkofs:
                tstp = self.bkofs
            p = raw_input(customWrap(_(
                "Choose a value for the current ambient brightness, consider "
                "that the more brightness there is, the more precise will the "
                "scale of the program be, supported values are backlight "
                "steps or percentage (eg. %d or %d%%, percentage *can* be "
                "over 100%% for particular needs): ") % (tstp, tpct)))
            try:
                if str(p)[-1] == '%':
                    percentage = float(str(p)[:-1])
                    curStep = int(round(
                        self.bkofs - 1 + percentage / (100.0 / self.steps), 0
                    ))
                    if curStep >= self.steps - 1 + self.bkofs:
                        curStep = self.steps - 1 + self.bkofs
                    cap.getScreenBri()
                    valThread.adjustValues(cap.scr)
                    try:
                        writeStep(curStep, self.bfile)
                    except IOError as err:
                        valThread.okToStop()
                        valThread.join(10)
                        brFileWriteErr(err, self.bfile)
                    dummy = query_yes_no(customWrap(_(
                            "Choosen percentage value roughly equals to the "
                            "%dth backlight step, would you like to use that "
                            "value?") % (curStep)), "yes")
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
                    dummy = query_yes_no(customWrap(_(
                            'Choosen backlight step value roughly equals to '
                            '%.2f%% of ambient brightness, would you like to '
                            'use that value?') % (percentage)), 'yes')
                    if dummy == 'yes':
                        break
                else:
                    fprnt(_(
                        'Please retry and enter a value according to the '
                        'rules above'))
                    time.sleep(1.5)
                print("")
            except ValueError:
                fprnt(_(
                    "Please retry and enter a value according to the rules "
                    "above") + '\n')
                time.sleep(1.5)
        valThread.okToStop()
        valThread.join(10)
        self.delta = (valThread.average - self.offset) / (percentage ** 1.372)
        return percentage, curStep

    def WritePassage(self):
        fprnt(_("Building a config file with the choosen settings..."))
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
        if self.lat is not None:
            config.set('Service', 'latitude', self.lat)
        if self.lon is not None:
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
        fprnt('>>> ' + _('config file saved as: %s') % self.configpath)
        if self.configpath == os.path.join('/etc', __LowerName__ + '.conf'):
            print("")
            fprnt(_(
                "This profile will always be read before any other user "
                "profile and user profiles read after it will (eventually) "
                "overwrite its settings.\n"
                "On the other hand, root user will *only* read that file."))
        elif os.path.basename(self.configpath) != 'default.conf':
            print("")
            fprnt(_(
                "To use the new profile add \"--profile %s\" to the "
                "switches") % (os.path.basename(self.configpath)[:-5]))
        if (
            not os.path.isfile(
                os.path.join('/etc', __LowerName__ + '.conf')) and
            os.path.basename(self.configpath) == 'default.conf'
        ):
            print("")
            fprnt(_(
                "You may want to use this profile as system-wide one; "
                "to achieve that copy \"%s\" to \"%s\"" % (
                    self.configpath,
                    os.path.join('/etc', __LowerName__ + '.conf'))
            ))
