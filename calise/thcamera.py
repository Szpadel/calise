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

from calise import pycamera
from calise.infos import __LowerName__


logger = logging.getLogger(".".join([__LowerName__, 'camera_thread']))


SendEvent = threading.Event()
GetEvent = threading.Event()
AbortEvent = threading.Event()


class CameraThread(threading.Thread):
    """ Camera Thread
    
    This class is one of calise's core threads and communicates directly
    with the main thread.
    
    After thread is initialized and started, a wait loop starts and the
    calling thread asks brightness values sending 'Get' events (as many
    as needed but just one at time)
    
    Makes use of all three 'Get', 'Send' and 'Abort' global events.
    
    """
    
    def __init__(self,device=None):
        self.brightness = None
        self.th = _CameraThreadFunctions(device)
        threading.Thread.__init__(name="camera")

    def run(self):
        self.th.capture_start()
        while True:
            brightness = self.th.set_brightness()
            if brightness is not None:
                self.brightness = brightness
                GetEvent.clear()
                SendEvent.set()
                # wait for "SendEvent" to be reset (calling thread
                # cleared event flag), to reset "self.brightness"
                while SendEvent.is_set():
                    time.sleep(0.0005)
                self.brightness = None
            # AbortEvent check is set on the bottom of the loop cycle
            # because "set_brightness()" already checks for that event
            # at the very start of execution.
            if AbortEvent.is_set():
                AbortEvent.clear()
                break
        self.th.capture_stop()


class _CameraThreadFunctions():
    """ calise.pycamera function wrapper
    
    This class is called only by "CameraThread" thread and cannot be
    accessed directly from outside.
    
    Makes use of 'Get', and 'Abort' global events.
    
    NOTE: this class puts on use "calise.pycamera" general functions
          specifically for calise needs. This should help for future
          individual calise.pycamera (core) code changes/upgrades.
    """
    
    def __init__(self,device=None):
        self.camera_module = pycamera.CameraProcess()
        self.camera_module.dev_init(device)
    
    def capture_start(self):
        self.camera_module.start_capture()
        self.camera_module.set_ctrls()
        # first (buffered) frame to be discarded (see pycamera module
        # for more info about camera C-module behaviour)
        self.camera_module.get_frame_brightness()
        
    def capture_stop(self):
        self.camera_module.reset_ctrls()
        self.camera_module.stop_capture()
        self.camera_module.freemem()

    def set_brightness(self):
        """ Capture event handler
        
        Waits for either a 'Get' or 'Abort' event to be set;
        'Abort' event takes over 'Proceed' one so that any pause/stop
        command has an almost immediate (but clean) effect.
        
        Could not use "wait()" method since any "AbortEvent" called
        during the "wait()" timeout (if any) won't get caught.
        
        """
        rc = True
        while rc is True:
            if AbortEvent.is_set():
                rc = None
            elif GetEvent.is_set():
                brightness = self.camera_module.get_frame_brightness()
                rc = brightness
            else:
                time.sleep(0.0005)
        return rc
