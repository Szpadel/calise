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


from calise import thcamera
from calise import thscreen


def sdev(values):
    average = sum(values) / float(len(values))
    dev = (sum([(x - average)**2 for x in values]) / float(len(values)))**.5
    return dev

def sdev_list_processor(values, threshold=1):
    ''' Standard deviation list check

    Perform a per-element standard deviation check, elements above or below
    standard deviation's threshold (which can be at most '1') are removed.

    '''
    avg = sum(values) / float(len(values))
    dev = sdev(values)
    corrected_values = list()
    for i in range(len(values)):
        if not values[i] > avg + max(dev, threshold) and \
           not values[i] < avg - max(dev, threshold):
                corrected_values.append(values[i])
    return corrected_values


class ServiceMainThread():

    def service_capture(self, number, sleeptime, threshold=1):
        ''' Service screen and camera capture function

        This function gets values from 'camera_thread' and
        (if loaded/availble) 'screen_thread'.
        
        To be sure that camera values are trustworthy, after 'number'
        captures have been taken, values are compared one-to-others
        upon standard deviation and, at each passage, wrong ones are
        discarded.
        If non-wrong values are less than 'number', another capture
        cycle is started withing the same capture session (maintaining
        correct values from previous cycles) until correct values are
        at least more than half of 'number'.

        '''
        values = list()
        self.camera_thread = thcamera.CameraThread(device)
        self.camera_thread.start()
        while not self.camera_thread.is_alive():
            time.sleep(0.01)
        # If "screen" module is loaded activate screen thread and ask
        # for a screen brightness capture (will only be checked) after
        # the whole camera block.
        if arguments['screen']:
            self.screen_thread = thscreen.ScreenThread()
            self.screen_thread.start()
            while not self.screen_thread.is_alive():
                time.sleep(0.01)
            thscreen.GetEvent.set()
        # outer camera cycle - End of screen block
        while len(values) < number * .5:
            # if not the first execution of the cycle warn
            if values:
                logger.warning("Capture precision is too low, requesting "
                               "additional captures")
            # inner camera cycle (capture)
            while len(values) < number:
                thcamera.GetEvent.set()
                starttime = time.time()
                thcamera.SendEvent.wait()
                thcamera.SendEvent.clear()
                temp_value = self.camera_thread.brightness
                values.append(temp_value)
                # Time between captures is calculated, removing the time
                # needed to get the frame from the camera.
                waittime = starttime + sleeptime - time.time()
                if waittime > 0:
                    time.sleep(waittime)
                logger.debug(
                    "raw values: %s" % 
                    ' '.join(["%4.1f" % k for k in values]))
            # After capture cycle ends, "number" captures have been
            # obtained. All values out of threshold range will be
            # removed.
            corrected_values = sdev_list_processor(values,threshold)
            while values != corrected_values:
                values = corrected_values
                corrected_values = sdev_list_processor(values,threshold)
            logger.debug(
                    "corrected values: %s" % 
                    ' '.join(["%4.1f" % k for k in values]))
        # At this point "values" has at least "number"/2 entries and its
        # data is reliable (max error < threshold).
        camera_value = float(sum(values)) / len(values)
        logger.debug("ambient_bri: %4.1f" % camera_value)
        thcamera.AbortEvent.set()
        # If "screen" module is loaded process the send request
        # returned from the corresponding thread and get screen
        # brightness value.
        if arguments['screen']:
            thscreen.SendEvent.wait()
            thscreen.SendEvent.clear()
            screen_value = self.screen_thread.brightness
            logger.debug("display_bri: %4.1f" % screen_value)
            screen_multiplier = self.screen_thread.multiplier
            thscreen.AbortEvent.set()
        # So far we have:
        #     - a reliable camera value average
        #     - (optional) a screen value (0% > 85% from center)
        #     - (optional) a screen-size multiplier
        #
        # TODO: Continue with functions that will process the above raw
        #       data.
        #
        # NOTE: Data-processing functions should be the same for both
        #       service_capture and application_capture.












# > BLOCK #01

    def get_brightness_percentage(camera_value, camera_min, camera_top):
        ''' Brightness percentage
        
        Obtain a percentage value, for camera brightness value passed to
        the fucntion, upon min and max values set by the user.
        
        NOTE: any 'camera_value' correction (eg. backlight brightness
              correction from fucntion 'get_brightness_correction')
              have to be applied BEFORE passing 'camera_value' to this
              function.
        '''
        if camera_min > camera_value:
            logger.warning("Camera brightness value (%.1f) is below minimum
                            level (%1f)" % (camera_value, camera_min))
            camera_value = camera_min
        percentage = 100 * ((camera_value - camera_min) / camera_top) ** 0.73
    
    def get_brightness_correction(screen_value, screen_multiplier,
                                  camera_value, camera_top, camera_min):
        ''' Backlight correction (in /255)
        
        (screen module only) Returns the amount of correction (in /255)
        to be applied to camera values in order to remove the
        brightness coming from the screen in front of the user.
        
        'fixed_camera_top' was the backlight intensity at which the
        screen of first test machine matched MAX backlight output:
        above that value (even if you couldn't see clearly) backlight
        couldn't be increased any further.

        NOTE: i -> backlight_intensity
              s -> display_brightness
              a -> ambient_brightness
              m -> max_correction
              l -> ambient_brightness_limit
        '''
        fixed_camera_top = 160.0
        i = (backlight_step / backlight_steps)*(camera_top) / fixed_camera_top
        s = screen_value / 255
        a = amb * (255.0 - offset) / 255
        m =  1.5 + 5 * (10*i - 1) * s**(3 - 1.3*i)
        l = fixed_camera_top * (255.0 - offset) / 255
        correction = m * (screen_multiplier ** 0.5) * ((l - a) / l)


# > BLOCK #02 
    
    def validate_backlight_device_path(path):
        ''' Validate given backlight path
        
        Validate if given backlight able device path (which can be
        either a directory path or a file path) is valid.
        
        Valdation is carried out in 2 passages: at first directory
        existence is checked and, if directory exists, search for 4 key
        files that should exist in there.
        
        '''
        devdir_content = [
            'brightness', 'max_brightness', 'bl_power', 'actual_brightness']
        # directory existence
        if os.path.isdir(path):
            device_path = path
        elif os.path.isdir(os.path.dirname(path)):
            device_path = os.path.dirname(path)
        else:
            device_path = None
        # basic directory validation
        if device_path:
            counter = 0
            for filename in devdir_content:
                if os.path.isfile(os.path.join(device_path, filename)):
                    counter += 1
            if counter != len(devdir_content):
                device_path = None
        # if given backlight device path got through both validation
        # passages, device_path is not None.
        return device_path

    def read_backlight(path, option):
        ''' Read one of backlight path values
        
        Given a backlight path value like brightness, bl_power, ...
        this function performs all necessary steps to get a clean
        reading of that path.
        (eg. read_backlight('/sys/class/backlight/acpi_video0', 'brightness')
        
        NOTE: ValueError and IOError have been excepted to be able to
              log them out, so that the user will know (and eventually
              easily fix) what's wrong.
        '''
        content = None
        devdir_content = [
            'brightness', 'max_brightness', 'bl_power', 'actual_brightness']
        device_path = validate_backlight_device_path(path)
        if not devdir_content.count(option):
            option = None
        if device_path and option:
            # check for path read permissions
            try:
                with open(os.path.join(device_path, option), 'r') as fp:
                    # check for path content (that should be a integer)
                    try:
                        content = int(fp.readline())
                    except ValueError:
                        logger.error(
                            "Choosen \'%s\' file (%s) is not valid\n" %
                            (option, device_path))
                        raise
            except IOError as err:
                if err.errno == errno.EACCES:
                    logger.error(
                        "Could not read from path \'%s\'. Please set at"
                        "least read permission for current user\n" %
                        os.path.join(device_path, option))
                raise
        return content
