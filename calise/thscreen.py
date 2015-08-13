#    Copyright (C)   2011-2014   Nicolo' Barbon
#
#    This file is part of Calise.
#
#    Calise is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published
#    by the Free Software Foundation, either version 3 of the License,
#    or any later version.
#
#    Calise is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Calise.  If not, see <http://www.gnu.org/licenses/>.


import math
import time
import threading
import logging

from calise import pyscreen
from calise.infos import __LowerName__


# Module properties
_properties = {
    'name': 'screen',
    'type': 'correction',
    'description':
        'Compute the amount to be subtracted from ambient brightness '
        'value (the one obtained from input modules) to remove the brightness '
        'coming from the screen.',
    'settings': {},
}
#Events definition
SendEvent = threading.Event()
GetEvent = threading.Event()
AbortEvent = threading.Event()
_logger = logging.getLogger(
    ".".join([__LowerName__, '%s_thread' % _properties['name']]))

#def get_info():
#    """ Get global module informations """
#    return _properties

def get_info(key=None):
    """ Get a specific key from global module informations """
    val = None
    if key and key in list(_properties):
        val = _properties[key]
    elif not key:
        val = _properties
    return val


def compute_correction(ambient,area,screen=0.0,backlight=0.0):
    """ Ambient brightness value correction

    These are the functions that give a fairly correct value of the
    amount of brightness to be removed from ambient brightness values.

    NOTE: I wasn't able to reverse the main correction function
          (actually it can't be reversed for most of its values since
          it is not bijective) so I blessed the computation capabilities
          of processors and brute-forced the result...

    WARNING: because of the non-bijectivity, errors may occur in ambient
             value range 15-35 with high backlight values.

             Just tested a bit:

                screen size           -> 19"
                screen backlight      -> 60%+
                xscreen brightness    -> 240+ (almost full white)
                brightness percentage -> 22%~28% (depends on user prefs)

             meaning that you may encounter errors only if the backlight is
             far above (more than double) the "suggested" value.

    max correction: -7.5 * (arctan(ambient/4.2 - 5.9) - pi/2)
    correction multiplier 1: 0.2*cor + (cor - 0.2*cor) * screen brightness
    correction multiplier 2: same with 'correction multiplier 1' instead of 'cor'
    correction multiplier result:
        0.04 + 0.16 * screen + 0.16 * backlight + 0.64 * screen * backlight

    """
    if None in [screen, backlight]:
        return ambient
    mult = (.04 + .16*screen + .16*backlight + .64*screen*backlight)*area
    n = 0
    p = 0.5  # computation pass (we don't need lab precision...)
    prev = -7.5 * (math.atan((ambient-n)/4.2 - 5.9) - math.pi/2)
    curr = -7.5 * (math.atan((ambient-n-p)/4.2 - 5.9) - math.pi/2)
    # If correction is needed, enter the loop-cycle.
    while not (
        max(prev*mult+(ambient-n), curr*mult+(ambient-n-p)) > ambient and
        min(prev*mult+(ambient-n), curr*mult+(ambient-n-p)) < ambient
    ):
        n += p
        prev = curr
        curr = -7.5 * (math.atan((ambient-n-p)/4.2 - 5.9) - math.pi/2)
    # Sistematic erorr averages in -0.5/+0.5 and so the value resulting from
    # correction is rounded up to an int (intended for 'camera' module only).
    corrected_value = round(sum([ambient-n, ambient-n-p])/2.0, 0)
    return corrected_value


class Configure():

    def __init__(self):
        print(_("%s module configuration") % (properties['name'].capitalize()))
        print("Nothing to configure yet.")


class MainThread(threading.Thread):
    """ Screen backlight Main Thread 
    
    This class is one of calise's core threads and communicates directly
    with the main thread.
    
    After thread is initialized and started, a wait loop starts and the
    calling thread asks brightness values sending 'Get' events (as many
    as needed)
    
    Makes use of 'Get', and 'Abort' global events.
    
    """
    
    def __init__(self):
        self.brightness = None
        self.multiplier = None
        self.th = _ScreenThreadFunctions()
        threading.Thread.__init__(name=properties['name'])

    def run(self):
        while True:
            brightness = self.th.set_brightness()
            multiplier = self.th.set_multiplier()
            if brightness is not None:
                self.brightness = brightness
                self.multiplier = multiplier
                GetEvent.clear()
                SendEvent.set()
                while SendEvent.is_set():
                    time.sleep(0.0005)
                self.brightness = None
                self.multiplier = None
            # AbortEvent check is set on the bottom of the loop cycle
            # because "set_brightness()" already checks for that event
            # at the very start of execution.
            if AbortEvent.is_set():
                AbortEvent.clear()
                break


class _ScreenThreadFunctions():
    """ calise.pyscreen function wrapper 
    
    This class is called only by "ScreenThread" thread and cannot be
    accessed directly from outside.
    
    Makes use of all three 'Get', 'Send' and 'Abort' global events.
    
    """
    def set_brightness(self):
        """ Capture event handler
        
        Waits for either a 'Get' or 'Abort' event to be set.
        
        Could not use "wait()" method since any "AbortEvent" called
        during the "wait()" timeout (if any) won't get caught.
        
        """
        rc = None
        while rc is None:
            if AbortEvent.is_set():
                rc = False
            elif GetEvent.is_set():
                brightness = pyscreen.get_screen_brightness()
                rc = brightness
            else:
                time.sleep(0.0005)
        return rc

    def set_multiplier(self):
        multiplier = pyscreen.get_screen_mul()
        return multiplier
    
    