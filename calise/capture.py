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
import Image
import signal
import errno
import time

from calise import camera
from calise import screenBrightness


# image capture class
# Manages image captures and 0 < 255 brightness value obtaining for both camera
# and screen
# Capture from camera: imaging.cam_get() > imaging.amb
# Capture from screen: imaging.scr_get() > imaging.scr
# Other functions can suit particular needs, but generally will not be needed
class imaging():

    def __init__(self):
        self.cameraobj = None  # v4l2 camera object
        self.cams = None       # available cameras
        self.webcam = None     # camera path (eg /dev/video)
        self.amb = None        # ambient brightness 0 < 255
        self.scr = None        # screen brightness 0 < 255

    # defines the camera to be used, path has to be a valid device path like
    # '/dev/video', if no path is given, first cam on pyGame cam list is taken
    def set_cam(self, path=None, auto=True):
        cam_list = camera.listDevices()
        if cam_list.count(str(path)) > 0:
            webcam = path
        else:
            webcam = cam_list[0]
        self.cams = cam_list
        self.webcam = webcam
        self.cameraobj = camera.Device()
        self.cameraobj.setName(self.webcam)
        if auto is True:
            self.start_cam()

    # initializes the pygame camera capture
    def start_cam(self, x=160, y=120):
        self.cameraobj.openPath()
        self.cameraobj.initialize()
        self.cameraobj.startCapture()

    # takes one image from the camera and calls image processor, finally
    # obtains %amb (ambient brightness in /255)
    # path specifications are the same from set_cam function
    #
    # threaded Timer and KillFunction are needed because of a non predictable
    # pyGame infinite process lock bug
    #
    def cam_get(self, path=None, x=160, y=120):
        if not self.cameraobj:
            self.set_cam(path, auto=False)
            self.start_cam(x, y)
        for x in range(2):
            val = None
            while val is None:
                try:
                    val = self.cameraobjreadFrame();
                except camera.Error as err:
                    if errno.EAGAIN == err[0]:
                        time.sleep(0.033)
                    else:
                        raise
            if x != 0:
                self.amb = val

    # unload the camera object
    def stop_cam(self):
        if self.cameraobj:
            self.cameraobj.stopCapture()
            self.cameraobj.uninitialize()
            self.cameraobj.closePath()
            self.cameraobj = None

    # obtains %scr (screen brightness in /255)
    def scr_get(self):
        if os.getenv('DISPLAY'):
            self.scr = int(screenBrightness.getDisplayBrightness())
        else:
            self.scr = 0.0
