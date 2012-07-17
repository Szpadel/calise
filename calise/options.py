#    Copyright (C)   2011-2012   Nicolo' Barbon
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
import argparse
import ConfigParser
from xdg.BaseDirectory import load_config_paths

from calise import optionsd


arguments = None  # arguments storage, every function updates that var


# Arguments Parser
def argsparser(argslist=None, version=None):
    parser = argparse.ArgumentParser(
        description=_(
            "Calculates ambient brightness and suggests (or sets) the "
            "screen's correct backlight using a webcam.\n"
            "For usage instructions type \"%(prog)s --help\"."))
    parser.add_argument(
        '--version',
        action='version',
        version='%s %s' % (parser.prog, version),
        help=_("displays current version and exits")
    )
    parser.add_argument(
        '--verbosity',
        metavar='N',
        dest='verbosity',
        type=int,
        default=None,
        help=argparse.SUPPRESS
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        dest='verbose',
        default=False,
        help=_("verbose output")
    )
    parser.add_argument(
        '--calibrate', '--configure',
        action='store_true',
        dest='cal',
        default=False,
        help=_("launches the calibration")
    )
    parser.add_argument(
        '--cam',
        metavar='path',
        dest='cam',
        default=None,
        help=_("cam to be used as capture device")
    )
    parser.add_argument(
        '--gap',
        metavar='N',
        dest='gap',
        default=None,
        type=float,
        help=_("sleep time between framecaptures, in seconds")
    )
    parser.add_argument(
        '--delta',
        metavar='N',
        dest='delta',
        default=None,
        type=float,
        help=_("equation\'s delta")
    )
    parser.add_argument(
        '--offset',
        metavar='N',
        dest='ofs',
        default=None,
        type=float,
        help=_("offset of the 0%% value of ambient brightness")
    )
    parser.add_argument(
        '--average',
        metavar='N',
        type=int,
        dest='avg',
        default=None,
        help=_("number of elements to average before changing backlight")
    )
    parser.add_argument(
        '--steps',
        metavar='N',
        type=int,
        dest='steps',
        default=None,
        help=_("number of backlight level steps (default: 10)")
    )
    parser.add_argument(
        '--invert',
        action='store_true',
        dest='invert',
        default=None,
        help=_(
            "choose if you have the backlight scale inverted (eg. 9 min - 0 "
            "max)")
    )
    parser.add_argument(
        '--bl-offset',
        metavar='N',
        type=int,
        dest='bkofs',
        default=None,
        help=_(
            "set if your backlight steps start from an arbitrary number (eg. "
            "2 min - 12 max instead of 0 min - 9 max)")
    )
    parser.add_argument(
        '--no-auto',
        action='store_false',
        dest='auto',
        default=None,
        help=_("disable automatic backlight level change")
    )
    parser.add_argument(
        '--no-screen',
        action='store_false',
        dest='screen',
        default=None,
        help=_("turns off screen\'s ambient brightness correction")
    )
    parser.add_argument(
        '--profile',
        dest='profile',
        default='default',
        help=_("uses the specified profile")
    )
    parser.add_argument(
        '--path',
        metavar='path',
        dest='path',
        default=None,
        help=_("location of the brightness backlight file")
    )
    parser.add_argument(
        '--logdata',
        action='store_true',
        dest='logdata',
        default=None,
        help=_(
            "Enables \"e\" key to export whole data from beginning, to "
            "calise.csv (if not set, only values within average range are "
            "exported). Be careful when using this option, because keeps "
            "every value obtained in memory, and that can lead to high memory "
            "usage if used for whole days. On the other hand, it\'s a great "
            "tool for experimental/statistic activities.")
    )
    parser.add_argument(
        '--logpath',
        metavar='path',
        dest='logpath',
        default=None,
        help=_("logdata save path (eg. /tmp/calise.csv)")
    )
    parser.add_argument(
        '--no-gui',
        action='store_false',
        dest='gui',
        default=None,
        help=_("Disables the graphical user interface")
    )
    global arguments
    arguments = parser.parse_args(argslist)


# Configuration files parser
# NOTE: Everything is done in optionsd, this is actually pretty useless
# TODO: ERASE & BURN the UGLYNESS!! (remove "pas" system ASAP)
def ParseCfgFile(pas=None):
    global arguments
    if pas is None:
        if arguments is None:
            pas = argsparser([])
        else:
            pas = arguments
    config = ConfigParser.RawConfigParser()
    pf = optionsd.profiler()
    for cf in optionsd.get_path(pas.profile):
        pf.check_config(cf)
    pas.cam = optionsd.settings['cam']
    pas.delta = optionsd.settings['delta']
    pas.ofs = optionsd.settings['offset']
    pas.steps = optionsd.settings['steps']
    pas.bkofs = optionsd.settings['bkofs']
    pas.invert = optionsd.settings['invert']
    pas.path = optionsd.settings['path']
    if optionsd.settings.keys().count('average'):
        pas.avg = optionsd.settings['average']
    if optionsd.settings.keys().count('delay'):
        pas.gap = optionsd.settings['delay']
    if optionsd.settings.keys().count('screen'):
        pas.screen = optionsd.settings['screen']
    arguments = pas
