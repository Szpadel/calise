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
import math
import threading
import time
import ConfigParser
from xdg.BaseDirectory import load_config_paths

from calise import camera
from calise import optionsd
from calise.system import computation
from calise.capture import imaging, processList, sDev


def UdevQuery(interface='/dev/video0'):
    ''' Query interface's sysfs infos

    Perform few queries to sysfs info paths to get detailed informations about
    camera device.
    Information obtained are then stored in a dictionary: 'UDevice'.

    '''
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


def searchExisting(camera=None, bfile=None, coordinates=None):
    ''' Search existing data among profiles

    Search for either given camera, brightness-path or coordinates in main
    profiles; only returns first profile found.

    TODO: Search every valid profile found in config paths and return a list
          of profiles, ordered from higher to lower level.
    '''
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


class calCapture (threading.Thread):
    ''' Frame-capture thread for calibration

    It's similar to the default non-service capture class but comes with few
    customizations specifically added for calibration passages 6 and 7.
    Especially, capture behaviour is set as follows: function takes values from
    the camera until okToStop() is called.

    '''
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

    # return the number of captures done by the capture function
    def getValCounter(self):
        return self.cap.counter

    def adjust_scale(self, cur=0):
        # set_flt needs a step value on the scale 0 < 100, so, if there's a
        # different scale/offset, it has to be set to a 0 < 100 one.
        return (cur - self.bkofs + 1) * (100.00 / self.steps)

    def adjustValues(self, scr):
        ''' Screen compensation correction

        Screen compensation correction function customized for calibration.
        Takes a 255based screen brightness value and corrects all data indexes
        from last correction (from 0 if the first one). Actually replaces a
        similar code sequence that was processed in "run" function.

        '''
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
        defInt = 2/30.0
        startTime = time.time()
        self.data = self.cap.getFrameBri(interval=defInt, loop=True, keep=True)
        fps = sum(self.data) / (time.time() - startTime)
        del self.data[:-(int(10 * fps))]
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
        import sys
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

