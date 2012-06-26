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
from pygame import camera, image
import signal
import threading

from calise import screenBrightness


# image capture class
# Manages image captures and 0 < 255 brightness value obtaining for both camera
# and screen
# Capture from camera: imaging.cam_get() > imaging.amb
# Capture from screen: imaging.scr_get() > imaging.scr
# Other functions can suit particular needs, but generally will not be needed
class imaging():

    def __init__(self):
        self.__cam = None   # pygame camera object
        self.cams = None    # available cameras
        self.__app = None   # QtApplication for screenshot
        self.webcam = None  # camera path (eg /dev/video)
        self.amb = None     # ambient brightness 0 < 255
        self.scr = None     # screen brightness 0 < 255

    # defines the camera to be used, path has to be a valid device path like
    # '/dev/video', if no path is given, first cam on pyGame cam list is taken
    def set_cam(self, path=None, auto=True):
        camera.init()
        cam_list = camera.list_cameras()
        if cam_list.count(str(path)) > 0:
            webcam = path
        else:
            webcam = cam_list[0]
        self.cams = cam_list
        self.webcam = webcam
        if auto is True:
            self.start_cam()

    # initializes the pygame camera capture
    def start_cam(self, x=160, y=120):
        self.__cam = camera.Camera(self.webcam, (x, y))
        self.__cam.start()

    # takes one image from the camera and calls image processor, finally
    # obtains %amb (ambient brightness in /255)
    # path specifications are the same from set_cam function
    #
    # threaded Timer and KillFunction are needed because of a non predictable
    # pyGame infinite process lock bug
    #
    def cam_get(self, path=None, x=160, y=120):
        if not self.__cam:
            self.set_cam(path, auto=False)
            self.start_cam(x, y)
        t = threading.Timer(5.0, self.KillFunction)
        t.start()
        self.rawim = self.__cam.get_image()
        t.cancel()
        sim = image.tostring(self.rawim, 'RGB')
        del self.rawim
        self.amb = self.imgproc((x, y), sim)

    # simply force kills if timer triggered
    def KillFunction(self):
        print "\n  ====  BLOCKED  ====  \r"
        import signal
        os.kill(os.getpid(), signal.SIGKILL)

    # unload the camera object
    def stop_cam(self):
        if self.__cam:
            self.__cam.stop()
            self.__cam = None
            camera.quit()

    # obtains %scr (screen brightness in /255)
    def scr_get(self):
        if os.getenv('DISPLAY'):
            self.scr = int(screenBrightness.getDisplayBrightness())
        else:
            self.scr = 0.0

    # processes a with,heigth,bytecdode input image and returns its average
    # brightness
    def imgproc(self, strsz=tuple, string=str, re_size=None, mode='RGB'):
        if re_size:
            if type(re_size) != tuple:
                raise TypeError("need tuple, %s found" % (type(re_size)))
        im = Image.fromstring(mode, (strsz[0], strsz[1]), string)
        if strsz[1] > 3:
            aspect = float(strsz[0]) / float(strsz[1])
            strsz = int(aspect * 3), 3
        im = im.resize((strsz[0], strsz[1]), Image.NEAREST)
        pix = im.load()
        lit = []
        for px in range(strsz[0]):
            for py in range(strsz[1]):
                (r, g, b) = (pix[px, py])
                lit.append(.299 * r + .587 * g + .114 * b)
        return sum(lit) / len(lit)
