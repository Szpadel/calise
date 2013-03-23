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
import time
from random import random
from xdg.BaseDirectory import save_config_path
import textwrap
from select import select

from calise.calibration.functions import *
from calise.calibration.interactiveui import setBrightness
from calise import console
from calise.infos import __LowerName__
from calise.capture import imaging
from calise.system import computation
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
            return default
        elif choice in valid.keys():
            return valid[choice]
        else:
            print valid.keys()
            sys.stdout.write(_(
                "Please respond with 'yes' or 'no' ('y' or 'n')") + ".\n")


class CliCalibration():
    ''' Wizard-style configuration

    Every "passage" has a short introduction that describes what does it do,
    then there's the function and newly generated values (from self or simply
    returned) are printed after a ">>> " string.
    
    NOTE: cfn > ConfigFileName, bfp > BrightnessFilePath

    '''
    def __init__(self, bfp=None):

        # Profile name passage
        fprnt("Step 1 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage gets a valid profile name to be stored as config "
            "file\'s filename."))
        profileName = self.ProfileFilenamePassage()
        fprnt(">>> " + _("profile name: %s") % str(profileName))
        fprnt(">>> " + _("profile path: %s") % str(self.configpath))
        fprnt("\n")

        # Sysfs backlight path passage
        fprnt("Step 2 of 7\n⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺")
        fprnt(_(
            "This passage lists all available sysfs backlight directories "
            "and, if more than one, asks wich has to be used."))
        self.BacklightPathPassage(bfp)
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

    def ProfileFilenamePassage(self):
        """ Obtains a valid profile filename
        
        (non-root user) If profile name is not already set (e.g.: default.conf)
        the user is asked for a profile name.
        
        (root user) Profile name and path are already set to "/etc/calise" and 
        "default.conf"
        
        NOTE: pn ~ ProfileName
        
        """
        pn = None
        defaultPath = os.path.join(
            save_config_path(__LowerName__), 'default' + '.conf')
        if not os.path.isfile(defaultPath):
            pn = 'default'
        if pn is None and os.getuid() != 0:
            while True:
                pn = raw_input(customWrap(_(
                    "Please, enter a name for the new profile") + ": "))
                if pn != pn + os.path.dirname(pn) or pn == "":
                    fprnt(_("Please retry and enter a valid name."))
                    fprnt(_(
                        "Since it\'ll be a filename, chars not supported by "
                        "your os will raise an error") + '\n')
                    time.sleep(1.5)
                elif os.listdir(save_config_path(__LowerName__)).\
                    count(pn + ".conf") > 0:
                    dummy = query_yes_no(customWrap(_(
                        "A profile file with the same name already exists, "
                        "overwrite?")), 'no')
                    if dummy == 'yes':
                        break
                else:
                    break
                sys.stdout.write('\n')
            self.configpath = os.path.join(
                save_config_path(__LowerName__), pn + '.conf')
        elif os.getuid() == 0:
            pn = __LowerName__
            configpath = os.path.join('/', 'etc', pn + '.conf')
            if os.path.isfile(configpath):
                dummy = query_yes_no(customWrap(_(
                    "A global profile already exists, overwrite?")), 'no')
                if dummy == 'no':
                    sys.exit(11)
            self.configpath = configpath
            pn = None
        else:
            self.configpath = os.path.join(
                save_config_path(__LowerName__), pn + '.conf')
        return pn

    # Gets sys/class/backlight infos
    def BacklightPathPassage(self, brPath=None):
        if not brPath:
            bfile_list = []
            scb = os.path.join("/", "sys", "class", "backlight")
            for bd in os.listdir(scb):
                brPath = os.path.join(str(scb), str(bd), 'brightness')
                if os.path.isfile(brPath):
                    bfile_list.append(brPath)
        else:
            self.bfile = brPath
            return self.bfile
        if len(bfile_list) == 1:
            self.bfile = bfile_list[0]
            return self.bfile
        elif len(bfile_list) == 0:
            sys.stderr.write('\n')
            sys.stderr.write(_(
                "Your system does not appear to have controllable "
                "backlight interfaces") + '\n')
            sys.exit(1)
        fprnt('\n' + '\n'.join(
            ["%d: %s" % (x + 1, bfile_list[x]) for x in range(len(bfile_list))]
        ))
        sys.stdout.write('\n')
        while True:
            tbfile = None
            bfile_idx = raw_input(customWrap(_(
                "Choose one of the paths listed above (None=%d): ") % 1))
            try:
                if bfile_idx == '':
                    tbfile = bfile_list[0]
                elif int(bfile_idx) <= len(bfile_list) and int(bfile_idx) > 0:
                    tbfile = bfile_list[int(bfile_idx) - 1]
                else:
                    fprnt(_(
                        "Please retry and enter an integer within the "
                        "valid range 1-%d!") % len(bfile_list))
            except ValueError, err:
                fprnt(_("Please retry and enter an integer!"))
            # Backlight test, write minimum then maximum supported value twice,
            # the user can test if selected interface was the right one
            if tbfile:
                tcv = readInterfaceData(tbfile)
                for x in range(2):
                    writeInterfaceData(tbfile, getMinimumLevel(tbfile))
                    time.sleep(.33)
                    writeInterfaceData(tbfile, readInterfaceData(
                        os.path.join(os.path.dirname(tbfile), 'max_brightness')
                    ))
                    time.sleep(.33)
                writeInterfaceData(tbfile, tcv)
                dummy = query_yes_no(customWrap(_(
                    "Did the screen just \"blink\" twice?")), 'no')
                if dummy == 'yes':
                    self.bfile = tbfile
                    break
            sys.stdout.write('\n')
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
                "The program will now display an interactive bar to adjust "
                "backlight level (with left/right down/up arrow keys). Hit "
                "\'Return\' when done.") + '\n')
            bkofs = setBrightness(os.path.dirname(self.bfile))
            sys.stdout.write('\n')
            writeInterfaceData(self.bfile, step0.bkstp)
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
                "The program has found these coordinates (\"%s\": %s, %s) through "
                "geoip lookup, would you like to use these value?")
                % (geo['city'], lat, lon)), "yes")
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
            while valThread.getValCounter() < 40:
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
        while valThread.getValCounter() < 40:
            time.sleep(.1)
        fprnt(_("Capture thread started."))
        time.sleep(0.75)
        sys.stdout.write('\n')
        curStep = int(setBrightness(os.path.dirname(self.bfile)))
        sys.stdout.write('\n')
        percentage = (curStep + 1 - self.bkofs) * (100.0 / self.steps)
        cap.getScreenBri()
        valThread.adjustValues(cap.scr)
        valThread.okToStop()
        valThread.join(10)
        self.delta = (valThread.average - self.offset) / (percentage ** 1.372)
        return percentage, curStep

    def WritePassage(self):
        fprnt(_("Building a config file with the choosen settings..."))
        config = ConfigParser.RawConfigParser()
        config.add_section('Camera')
        config.set('Camera', 'device', str(self.camera))
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
