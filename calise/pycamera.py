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


import time
import errno
import logging

from calise import camera
from calise.infos import __LowerName__


logger = logging.getLogger(".".join([__LowerName__, 'camera']))


def udev_query(interface):
    """ Query interface's sysfs infos

    Perform few queries to sysfs info paths to get detailed
    informations about camera device.

    """
    UDevice = {
        'KERNEL': None,
        'DEVICE': None,
        'SUBSYSTEM': None,
        'DRIVER': None,
        'ATTR': {},}
    # KERNEL
    if os.path.islink(interface):
        link = os.readlink(interface)
        if link.startswith('/'):
            interface = link
        else:
            interface = '%s%s' % (os.path.dirname(interface), link)
    #UDevice['KERNEL'] = interface.split('/')[-1]
    UDevice['KERNEL'] = interface
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

def remove_fakes(paths):
    """ Remove duplicate/linked paths """
    for i in range(len(paths)):
        cp = paths[i]
        if os.path.islink(cp):
            link = os.readlink(cp)
            if link.startswith('/'):
                paths[i] = link
            else:
                paths[i] = '%s%s' % (cp.replace(cp.split('/')[-1], ''), link)
    paths.sort()
    last = paths[-1]
    for i in range(len(paths) - 2, -1, -1):
        if last == paths[i]:
            del paths[i]
        else:
            last = paths[i]

def get_available_devices():
    """ Get all V4L2 devices

    Build up a disctionary with device paths indexes containing all
    informations obtained from a per device udev_query().

    """
    devices = []
    device_paths = camera.listDevices()
    if not device_paths:
        raise CameraError(2, "No available cameras found.")
    device_paths = remove_fakes(device_paths)
    for path in device_paths:
        devices.append(udev_query(path))
    return devices


# default (and pretty simple) Error for camera class
class CameraError(Exception):

    def __init__(self, code, value):
        self.errno = code
        self.value = value

    def __str__(self):
        fmtstr = "[Errno %d] %s" % (self.errno, self.value)
        return fmtstr


class CameraProcess():
    """ Camera functions

    NOTE: after the camera is initialized and a capture session is
          started, the function "get_frame_brightness" can be executed
          as many consecutive times as needed (one at time). When you
          are done with "get_frame_brightness" executions, finalize the
          capture session and clear the memory.
    """

    def __init__(self):
        self.device = None  # v4l2 camera object
        self.device_paths = None  # available v4l2 cameras
        self.device_path = None  # camera path (eg /dev/video)
        self.ctrls = {}  # camera controls (queried ones) dictionary
        self.device_status = None  # camera power on/off flag

    def dev_init(self, path=None):
        """ Camera device inizialization

        Define the camera to be used for this session's CameraObj. Path
        has to be a valid device path like '/dev/video', if no path is
        given, first device from v4l2 capture device list is picked.

        """
        device_paths = camera.listDevices()
        if not device_paths:
            raise CameraError(2, "No available cameras found.")
        self.device_paths = device_paths
        if device_paths.count(str(path)):
            device_path = path
        else:
            logger.warning(
                "given camera ('%s') not among v4l2 supported devices, using "
                "first available camera ('%s') instead" % devices[0])
            device_path = device_paths[0]
        self.device_path = device_path
        self.device = camera.Device()
        self.device.set_name(self.device_path)

    def start_capture(self):
        """ Start a capture session

        Activate CameraObj (from initialization) camera allowing it to
        actually return frames.

        """
        if self.device_status is True:
            return
        self.device.open_path()
        self.set_ctrls()
        try:
            self.device.initialize()
        except camera.Error as err:
            if err[0] == errno.EBUSY:
                logger.error(err[1].rstrip('\n'))
                self.reset_ctrls()
                self.device.close_path()
                #raise KeyboardInterrupt --COMMENTED OUT--
                raise err
        self.device.start_capture()
        self.device_status = True

    def stop_capture(self):
        """ Stop a capture session

        Deactivate CameraObj camera. To capture more frames after this
        point a new capture session has to be launched.

        """
        if self.device_status is False:
            return
        self.device.stop_capture()
        self.device.uninitialize()
        self.reset_ctrls()
        self.device.close_path()
        self.device_status = False

    def freemem(self):
        """ Free device object (to re-inizialize or on TERMINATE)

        NOTE: This has to be executed after a capture session has been
              stopped or even before starting a capture. Launching with
              the camera active will make the program not able to catch
              the camera back.
        """
        del self.device
        self.device = None

    def query_ctrls(self):
        """ Query device controls

        Query the device for 3 specific controls that may modify
        (pretty much unpredictably) brightness values obtained:

        (12) V4L2_CID_AUTO_WHITE_BALANCE
        (18) V4L2_CID_AUTOGAIN
        (28) V4L2_CID_BACKLIGHT_COMPENSATION

        """
        controls = {
            'V4L2_CID_AUTO_WHITE_BALANCE': 12,
            'V4L2_CID_AUTOGAIN': 18,
            'V4L2_CID_BACKLIGHT_COMPENSATION': 28,}
        for x in [controls[k] for k in list(controls.keys())]:
            try:
                tmp = self.device.query_ctrl(x)
                self.ctrls[str(x)] = {
                    'id': tmp[0],
                    'name': tmp[1],
                    'min': tmp[2],
                    'max': tmp[3],
                    'step': tmp[4],
                    'default': tmp[5],
                    'old': tmp[6],
                    'new': None,}
            except camera.Error as err:
                if err[0] != errno.EINVAL:
                    raise
                # EINVAL means control is not available (errorcode 22)
                logger.warning(
                    "\'v4l2-%s\' is not available on the selected device." %
                    (self.ctrls[idx]['name']))
                continue
        return self.ctrls

    def set_ctrls(self):
        """ Disable any control in ctrls.keys()

        NOTE: A dictionary with existing settings is saved for later
              restoration.
        """
        if self.ctrls is None:
            self.ctrls = self.query_ctrls()
        for x in [int(k) for k in self.ctrls.keys()]:
            idx = str(x)
            # for controls 12, 18 and 28 *min* means disable control
            if self.ctrls[idx]['old'] != self.ctrls[idx]['min']:
                self.device.set_ctrl(x, self.ctrls[idx]['min'])
                logger.debug(
                    "\'v4l2-%s\' set from %s to %s" %
                    (self.ctrls[idx]['name'],
                     self.ctrls[idx]['old'],
                     self.ctrls[idx]['min']))
            self.ctrls[idx]['new'] = self.ctrls[idx]['min']

    def reset_ctrls(self):
        """ Restore any modified camera control

        NOTE: Does't reset to "factory default" but to the values found
              by 'set_ctrls' function before they were changed, this
              means that this function HAS to be executed only after
              'set_ctrls'.
        """
        for x in [int(k) for k in self.ctrls.keys()]:
            idx = str(x)
            # raise if somehow 'new' has not been initialized
            if self.ctrls[idx]['new'] is None:
                raise CameraError(
                    5, "Control not initialized for \'%s\' (%d)" %
                    (self.ctrls[idx]['name'], x))
            if self.ctrls[idx]['new'] != self.ctrls[idx]['old']:
                self.device.set_ctrl(x, self.ctrls[idx]['old'])
                logger.debug(
                    "\'v4l2-%s\' restored to %s from %s" %
                    (self.ctrls[idx]['name'],
                     self.ctrls[idx]['old'],
                     self.ctrls[idx]['new']))

    def get_frame_brightness(self):
        """ Get brightness from a camera frame

        Inside the C module camera takes a 160x120 picture and computes
        its brightness. If camera is not ready yet, a CameraError.EAGAIN
        is raised.

        NOTE: Since camera capture (in camera C-module) has been set
              with flag "O_NONBLOCK", until at least 1 buffer is free
              on the camera, asking for a capture will raise V4L2.EAGAIN
              error.
              A loop cycle is set to ask until valid value is returned
              but there's also an error exception to avoid buffer
              lock-ups (default timeout 5 seconds).

        NOTE: (for higher level apps) C-module has 1 frame buffered so
              it's needed to have 2 captures to get the *real* frame.
        """
        timeout = time.time()
        frame_brightness = None
        while frame_brightness is None:
            try:
                frame_brightness = self.device.read_frame()
            except camera.Error as err:
                if time.time() - timeout > 5:
                    if errno.EAGAIN == err[0]:
                        self.stop_capture()
                        logger.error(
                            "Unable to get a frame from the camera: "
                            "device is continuously returning "
                            "V4L2.EAGAIN (Try Again). 5 seconds anti-lock "
                            "timer expired, discarding capture session.")
                    raise err
                elif errno.EAGAIN == err[0]:
                    time.sleep(1.0 / 30.0)  # 1/30 sec is arbitrary
                else:
                    raise err
        return frame_brightness
