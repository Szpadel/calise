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


import sys
import time
import threading

from calise import pycamera
from calise.infos import __LowerName__


# Module properties
_properties = {
    'name': 'camera',
    'type': 'input',
    'description':
        'Obtain ambient brightness values from any V4L2 compatible camera '
        'device.',
    'settings': {'device': str, 'offset': int},
}
# Events definition
SendEvent = threading.Event()
GetEvent = threading.Event()
AbortEvent = threading.Event()
_logger = logging.getLogger(
    ".".join([__LowerName__, '%s_thread' % _properties['name']]))

def get_infos():
    """ Get global module informations """
    return _properties

def get_info(key):
    """ Get a specific key from global module informations """
    val = None
    if key in list(_properties):
        val = _properties[key]
    return val


class Configure():

    def __init__(self):
        self.th = _CameraThreadFunctions()
        print(
            _("%s module configuration") % (_properties['name'].capitalize()))

    def conf_device(self):
        """ Device sysfs informations setting

        Set global _properties['setting']['device'] to sysfs device
        infos.

        NOTE: Must be executed *before* conf_offset, otherwise the
              latter won't have required data.
        """
        devices = self.th.get_devices()
        default_index = 0
        if len(devices) == 1:
            index = default_index
        elif len(devices) > 1:
            # Print a list with all available devices
            index = 0
            for device in devices:
                sys.stdout.write("%d: %s" % (index + 1, device['KERNEL']))
                if list(device['ATTR'].keys()).count('name'):
                    sys.stdout.write(" %s" % (device['ATTR']['name']))
                sys.stdout.write("\n")
                index += 1
            # Ask the user to pick one of the devices previously listed
            while True:
                selection = raw_input(
                    _("Choose one of cams listed above (default=%s): ") %
                    devices[default_index]['KERNEL']))
                if type(selection) != int and selection != '':
                    print(_("Please retry and enter an integer."))
                elif int(selection) > len(devices) or int(selection) < 1:
                    print(_("Please retry and enter an integer within the "
                            "valid range 1-%d.") % len(devices))
                elif selection == '':
                    index = default_index
                    break
                elif int(selection) <= len(devices) and int(selection) > 0:
                    index = selection - 1
                    break
                sys.stdout.write("\n")
        # Set global $device variable
        global _properties
        _properties['settings']['device'] = devices[index]

    def conf_offset(self):
        """ Device's brightness offset setting

        Set global _properties['settings']['offset'] to the minimum
        possible brightness that can be captured from the device.

        A lot of webcams never get 0/255 brightness value even with
        white_balance, and similar controls turned off.
        In most cases this doesn't mean that captured values are not
        trustworthy but it just means that x/255 values are actually
        x/255-offset values and correcting this offset lead to
        precise capture values.

        NOTE: Since every camera device gets different capture values
              with similar brightness conditions, the actual precision
              is not that relevant, you just need to have an input
              device that give 0 > 255 values as requested to every
              input modules.
        """
        self.th.initialize(_properties['settings'])
        raw_input(customWrap(
            _("Cover the webcam and then press [ENTER] or [RETURN]")))
        values = []
        self.th.capture_start()
        for x in range(40):
            GetEvent.set()
            brightness = self.th.set_brightness()
            if brightness is not None:
                values.append(brightness)
                GetEvent.clear()
        self.th.capture_stop()
        global _properties
        _properties['settings']['offset'] = min(values)


class MainThread(threading.Thread):
    """ Camera Main Thread

    This class is one of calise's core threads and communicates directly
    with the main thread.

    After thread is initialized and started, a wait loop starts and the
    calling thread asks brightness values sending 'Get' events (as many
    as needed but just one at time)

    Makes use of all three 'Get', 'Send' and 'Abort' global events.

    """

    def __init__(self,settings):
        self.brightness = None
        self.th = _CameraThreadFunctions(settings)
        threading.Thread.__init__(name=_properties['name'])

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

    This class is called only by "MainThread" thread and shouldn't be
    accessed directly from outside.

    Makes use of 'Get', and 'Abort' global events.

    NOTE: this class puts on use "calise.pycamera" general functions
          specifically for calise needs. This should help for future
          individual calise.pycamera (core) code changes/upgrades.
    """

    def __init__(self,settings=None):
        self.camera_module = pycamera.CameraProcess()
        if settings:
            self.initialize(settings)

    def initialize(self,settings):
        self.camera_module.dev_init(settings['device']['KERNEL'])
        self.offset = settings['offset']

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
                # normalize value as /255 removing any base offset
                rc = (brightness - self.offset) / (255 - self.offset) * 255
            else:
                time.sleep(0.0005)
        return rc

    def get_controls(self):
        """ Get brightness related device controls """
        controls = self.camera_module.query_ctrls()
        return controls

    def get_devices(self):
        """ Get a list of all v4l2 compatible devices """
        devices = self.camera_module.get_available_devices()
        return devices
