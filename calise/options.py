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


# TODO: moduli base = camera, screen, geoip, weather, acpi,
#       e.g. camera=/dev/video0:30,screen=::2,acpi


import sys
import argparse


__version__ = '1.0.0-a1'  # TODO: delete this line
settings = dict()

# NOTE: requires active_modules
def build_modules_options():
    options = dict()
    for module in active_modules:
        name = module.get_info('name')
        settings = module.get_info('settings')
        options[str(module)] = dict([(k, settings[k]) for k in list(settings)])
        options[str(module)]['active'] = bool
    return options

def build_options():
    options = dict()
    options['modules'] = build_modules_options()
    options['service'] = {
        'latitude': float,
        'longitude': float,
        'capture-number': int,
        'capture-interval': float,
        'geoip': bool,
        'weather': bool,
        'day-sleeptime': float,
        'night-sleeptime': float,
        'twilight-multiplier': float,}
    options['daemon'] = {
        'latitude': float,
        'longitude': float,
        'capture-number': int,
        'capture-interval': float,
        'geoip': bool,
        'weather': bool,
        'day-sleeptime': float,
        'night-sleeptime': float,
        'twilight-multiplier': float,}
    options['advanced'] = {
        'average': int,
        'capture-delay': float,}
    options['info'] = {
        'loglevel': str,
        'logfile': str,}
    return options


# Command line parser
def cli_parser():
    parser = argparse.ArgumentParser(
        description=("Computes brightness values from input modules and "
                     "executes output modules."),
        prog="calise")
    parser.add_argument(
        '--version',
        action='version',
        version='%(pro)s %(ver)s' % dict(pro='%(prog)s', ver=__version__),
        help="display current version")
    # Service execution
    parser.add_argument(
        '-k', '--stop',
        action='store_true', dest='kill',
        help="terminate service")
    parser.add_argument(
        '-e', '--pause',
        action='store_true', dest='pause',
        help="pause service")
    parser.add_argument(
        '-r', '--resume',
        action='store_true', dest='resume',
        help="resume service from \"pause\" state")
    parser.add_argument(
        '-c', '--capture',
        action='store_true', dest='capture',
        help="do a capture and set backlight accordingly")
    parser.add_argument(
        '--check',
        action='store_true', dest='check',
        help="check whether service is running or not")
    # Modules
    parser.add_argument(
        '-m', '--modules',
        metavar='<module1[=opt1[:opt2]],module2,...>', dest='mline',
        help=(
            "load modules and eventually module settings. To disable modules "
            "loaded by default add the \"no\" suffix (eg. nocamera). "
            "If no option is specified for modules, profile defaults "
            "will be loaded.\n"
            "To see a list of available modules to use, type -m list\n"
            "To see any module options, type -m <module>=help"))
    # Variable set
    parser.add_argument(
        '-p', '--profile',
        metavar='<profile>', dest='profile', default='default',
        help="specify either a valid profile name or path")
    parser.add_argument(
        '--location',
        metavar='<lat>:<lon>', dest='position',
        help="set geographical position expressed as float degrees")
    parser.add_argument(
        '--twilight-mul',
        metavar='<float>', dest='dusksm',
        help="set the capture sleeptime multiplier for twilights ")
    parser.add_argument(
        '--day-sleeptime',
        metavar='<float>', dest='dayst',
        help=(
            "set maximum seconds between captures during the day "
            "(default: 300)"))
    parser.add_argument(
        '--night-sleeptime',
        metavar='<float>', dest='nightst',
        help=(
            "set seconds between captures at night; 0 means no captures "
            "(default)"))
    # Logging
    parser.add_argument(
        '--loglevel',
        metavar='<level>', dest='loglevel',
        help="log level: error, warning, info (default) or debug")
    parser.add_argument(
        '--logfile',
        metavar='<path>', dest='logfile',
        help=(
            "log output file (tempfile inside calise tempdir if not "
            "specified)"))
    parser.add_argument(
        '-d', '--dump',
        action='store_true', dest='dump',
        help="dump last capture data")
    parser.add_argument(
        '-a', '--dump-all',
        action='store_true', dest='dumpall',
        help="dump all captured data from program start")
    parser.add_argument(
        '--dump-settings',
        action='store_true', dest='dumpsettings',
        help="dump current execution's settings")
    #arguments = vars(parser.parse_args(cli_arguments))
    return parser

def assign_mvalues(msettings):
    ''' Compile a dictionary from given list
    
    Compile a dictionary with the first entry of the list as index and the 
    eventual second one as value.
    If no second list entry is given, the dictionary index will get to None as
    value.
    '''
    retval = dict()
    if len(msettings) == 1:
        retval[msettings[0]] = ""
    elif len(msettings) > 1:
        retval[msettings[0]] = msettings[1]
    else:
        raise ValueError
    return retval

def separate(line, separator):
    ''' Compile value list
    
    Line is split according to given separator, then the first entry becomes
    list's first entry while all remaining entries become list's second entry.
    '''
    tmpval = line.split(separator)
    if len(tmpval) == 1:
        retval = [tmpval[0]]
    elif len(tmpval) > 1:
        retval = [tmpval[0], separator.join(tmpval[1:])]
    else:
        raise ValueError
    return retval

# illegal character ","
def parse_cli_modules(cli_modules):
    modules = dict()
    tmpmod = cli_modules.split(',')
    for entry in tmpmod:
        tmpval = assign_mvalues(separate(entry, '='))
        keyname = tmpval.keys()[0]
        modules[keyname] = dict()
        if not tmpval[keyname]:
            continue
        for value in tmpval[keyname].split(':'):
            modules[keyname].update(assign_mvalues(separate(value,'=')))
    return modules

def parse_config(conf, opt):
    # parse keys from options dictionary as self.settings keys
    for j in opt.keys():
        for key in opt[j]:
            if config.has_option(j, key):
                vtype = self.options[j][key]
                if int == vtype:
                    settings[key] = config.getint(j, key)
                elif float == vtype:
                    settings[key] = config.getfloat(j, key)
                elif bool == vtype:
                    settings[key] = config.getboolean(j, key)
                else:
                    settings[key] = config.get(j, key)



if __name__ == '__main__':
    #aaa = parse_cli_modules('module1,module2=a:b=3,nomodule3,module4=z=4:c=gfd=k&j:h')
    #for entry in aaa.keys():
    #    print(entry, aaa[entry])
    parser = cli_parser()
    lel = parser.parse_args()
    for entry in zez.keys():
        if zez[entry] is False or zez[entry] is None:
            del zez[entry]
    print(zez)
    if zez.keys().count('profile'):
        
























'''
class profiler():

    # options syntax:
    #   Group: {option: data_type}
    #   Group: {option: (data_type, self.settings_key)} TODO: delete this line
    options = {
        'Camera': {
            'offset': (float, 'offset'),
            'delta': (float, 'delta'),
            'camera': (str, 'cam'),
            'device': (str, 'cam'),
        },
        'Backlight': {
            'steps': (int, 'steps'),
            'offset': (int, 'bkofs'),
            'invert': (bool, 'invert'),
            'path': (str, 'path'),
        },
        'Service': {
            'latitude': (float, 'latitude'),
            'longitude': (float, 'longitude'),
            'capture-number': (int, 'capnum'),
            'capture-interval': (float, 'capint'),
            'geoip': (bool, 'geoip'),
            'weather': (bool, 'weather'),
            'day-sleeptime': (float, 'dayst'),
            'night-sleeptime': (float, 'nightst'),
            'twilight-multiplier': (float, 'dusksm'),
            },
        'Daemon': {
            'latitude': (float, 'latitude'),
            'longitude': (float, 'longitude'),
            'capture-number': (int, 'capnum'),
            'capture-interval': (float, 'capint'),
            'geoip': (bool, 'geoip'),
            'weather': (bool, 'weather'),
            'day-sleeptime': (float, 'dayst'),
            'night-sleeptime': (float, 'nightst'),
            'twilight-multiplier': (float, 'dusksm'),
        },
        'Advanced': {
            'average': (int, 'avg'),
            'capture-delay': (float, 'gap'),
            'screen-compensation': (bool, 'screen'),
        },
        'Info': {
            'loglevel': (str, 'loglevel'),
            'logfile': (str, 'logfile'),
        },
    }

    def __init__(self):
        self.config = ConfigParser.RawConfigParser()

    def check_config(self, configFile):
        if os.path.isfile(configFile):
            try:
                self.config.read(configFile)
                logger.info("Profile found: %s" % configFile)
            except (
                ConfigParser.MissingSectionHeaderError,
                ConfigParser.ParsingError) as err:
                err = str(err).replace('\t', '').splitlines()
                logger.warning(err[0])
                for line in err[1:]:
                    logger.debug(line)
                return 1
            self.parse_config()
        return 0

    def parse_config(self, config=None):
        global settings
        if config is None:
            config = self.config
        # parse keys from options dictionary as self.settings keys
        for option in self.options.keys():
            for key in self.options[option]:
                if config.has_option(option, key):
                    vtype, skey = self.options[option][key]
                    if int == vtype:
                        settings[skey] = config.getint(option, key)
                    elif float == vtype:
                        settings[skey] = config.getfloat(option, key)
                    elif bool == vtype:
                        settings[skey] = config.getboolean(option, key)
                    else:
                        settings[skey] = config.get(option, key)

    def read_configs(self):
        for conf in get_path():
            self.check_config(conf)

class malapala():
'''