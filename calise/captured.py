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
import os

#from calise.capture import imaging
from calise import camera
from calise import screenBrightness


#caliseCapture = imaging()


def takeScreenshot():
    scr = 0.0
    if os.getenv('DISPLAY'):
        scr = int(screenBrightness.getDisplayBrightness())
    return scr


cs = None
class camsense():

    def __init__(self, device='/dev/video0'):
        self.cameraobj = camera.device()
        self.cameraobj.setName(device)

    def startCapture(self):
        self.cameraobj.openPath()
        self.cameraobj.initialize()
        self.cameraobj.startCapture()

    def takeFrames(self, number=10.0, interval=0.2):
        # buffered frame on v4l2 device (first X buffered frames are not
        # processed)
        cambuffer = 1
        camValues = []
        for x in range(number + 1):
            startTime = time.time()
            val = None
            while val is None:
                try:
                    val = self.cameraobj.readFrame()
                except camera.Error as err:
                    # except EAGAIN (temporary not available) error. Every cam
                    # has a maximum certain number of fps available, if called
                    # too early, EAGAIN is raised
                    if errno.EAGAIN == err[0]:
                        time.sleep(0.033)
                    else:
                        raise
            # first frame is buffered-frame so can be few seconds old, it's
            # simply not included in final array
            if x != 0:
                camValues.append(val)
                if x != (number - 1):
                    time.sleep(interval - (time.time() - startTime))
        return camValues

    def stopCapture(self):
        self.cameraobj.stopCapture()
        self.cameraobj.uninitialize()
        self.cameraobj.closePath()



# Picture taker (depends on gureatoCheck)
# Takes n frames, one every i secs and returns a list object.
# number: number of captures to be done each time a "capture" is asked
# interval: time interval between captures in a single "capture" session
def takeSomePic(number=10.0, interval=0.2):
    global cs
    if cs is None:
        cs = camsense()
    cs.startCapture()
    cv = cs.takeFrames(number, interval)
    cs.stopCapture()
    while True:
        nv = gureatoCheck(cv)
        if len(cv) == len(nv):
            break
        else:
            cv = nv
    return cv


# GURRRREATO CHECKER ONIZUKA
# Searches given values for discordant ones, then return a "cleared" list
def gureatoCheck(lista):
    devList = []
    for idx in range(len(lista)):
        newList = lista[:idx] + lista[idx + 1:]
        avg = sum(newList) / float(len(newList))
        dev = sDev(newList, avg)
        devList.append(dev)
    devListAvg = sum(devList) / len(devList)
    devListDev = sDev(devList, devListAvg)
    toBeErased = []
    for idx in range(len(lista)):
        try:
            if devListDev > 0.75 and \
                ((devList[idx] - devListAvg) ** 2) ** .5 > devListDev:
                del lista[idx]
        except IndexError:
            break
    return lista


# siple standard deviation function
def sDev(lista, average=None):
    if not average:
        average = sum(lista) / float(len(lista))
    dev = (sum([(x - average) ** 2 for x in lista]) / float(len(lista))) ** .5
    return dev
