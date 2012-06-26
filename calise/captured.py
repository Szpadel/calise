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

from calise.capture import imaging


caliseCapture = imaging()


def takeScreenshot():
    caliseCapture.scr_get()
    return caliseCapture.scr


# Picture taker (depends on gureatoCheck)
# Takes n frames, one every i secs and returns a list object.
# number: number of captures to be done each time a "capture" is asked
# interval: time interval between captures in a single "capture" session
def takeSomePic(number=7.0, interval=0.5):
    camValues = []
    for x in range(int(number)):
        caliseCapture.cam_get()
        camValues.append(caliseCapture.amb)
        if x < number - 1:
            time.sleep(interval)
    caliseCapture.stop_cam()
    while True:
        newVals = gureatoCheck(camValues)
        if len(camValues) == len(newVals):
            break
        else:
            camValues = newVals
    return camValues


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
