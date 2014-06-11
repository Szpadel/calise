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


import os
import logging

from calise import screen
from calise.infos import __LowerName__


logger = logging.getLogger(".".join([__LowerName__, 'monitor']))


def get_active_display():
    """ Obtain currently active display (if any)
    
    If current non-root user is operating on a Xorg session, the env
    var "DISPLAY" is returned, otherwise NoneType is returned.
    
    TODO: if current user is the root user this function should still 
          return current user's "DISPLAY" env var if any.
    """
    display = os.getenv('DISPLAY')
    return display

def get_screen_brightness():
    """ Obtain display image brightness
    
    Obtain display image average brightness through 'screen' C-module.
    The function returns FloatType or NoneType.
    
    """
    screen_brightness = None
    display = get_active_display()
    if display:
        screen_brightness = screen.get_brightness(display)
    return screen_brightness
    
def get_screen_mul():
    """ Obtain display coefficient multiplier
    
    Compare currently active monitor area (in mm) with the 17 inch
    16:10 diagonal monitor used when the screen backlight compensation
    module was first written (and tested).
    The function returns FloatType or NoneType.
    
    NOTE: doesn't take in consideration the actual screen backlight
          power (some screens are "brighter" than others) but since a
          "comfortable" backlight level of the monitor doesn't change
          much from person to person, this control should be actually
          pretty precise.
    """
    mul = None
    display = get_active_display()
    if display:
        mmsize = screen.get_size(display)
        if mmsize:
            mmx, mmy = mmsize
            refbase = (((17*25.4) ** 2) / (1.6**2 + 1.0**2)) ** .5
            refmmx = (float(mmx)/mmy) * refbase
            refmmy = refbase
            # multiplier arbitrary formula = (Area / AreaRef) ** 2
            mul = ((mmx*mmy) / float(refmmx*refmmy)) ** 2
    return mul
