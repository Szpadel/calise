#    Copyright (C)   2011-2013   Nicolo' Barbon
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


import time
import threading

from calise import pyscreen
from calise.infos import __LowerName__


logger = logging.getLogger(".".join([__LowerName__, 'screen_thread']))


SendEvent = threading.Event()
GetEvent = threading.Event()
AbortEvent = threading.Event()


class ScreenThread(threading.Thread):
    """ Screen Thread 
    
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
        threading.Thread.__init__(name="screen")

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
    
    