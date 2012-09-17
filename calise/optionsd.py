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
import argparse
import ConfigParser
import logging
from xdg.BaseDirectory import load_config_paths

from calise.infos import __LowerName__, __version__


# Store either interactive or service versionss settings
settings = {}

# Logging
logger = logging.getLogger('.'.join([__LowerName__, 'options']))

# Service commands definitions
execCommands = ['kill', 'restart', 'pause', 'resume', 'capture']
queryCommands = ['dump', 'dumpall', 'dumpsettings', 'check']
serviceCommands = execCommands + queryCommands

# Default service version's settings
defaultSettings = {
    'capnum': 14,
    'capint': 0.1,
    'loglevel': 'info',
    'logfile': None,
    'screen': True,
    'scrmul': None,
    'geoip': True,
    'weather': True,
    'dayst': 300.0,
    'dusksm': 0.7,
    'nightst': 0.0,
    'path': None,
}

# Default interactive version's settings
defIntSetings = {
    'gap': 0.67,
    'avg': int(round((90 / 0.67), 0)),
    'logfile': None,
    'screen': True,
    'scrmul': None,
    'auto': True,
    'configure': False,
    'record': False,
    'recfile': '%s.csv' % __LowerName__,
    'loglevel': 'warning',
    'logfile': None,
    'gui': True,
    'verbose': False,
    'path': None,
}


# Lookup for setting key and if not present, set necessary optionals to default
def checkSettingsArguments():
    for key in defaultSettings.keys():
        if not key in settings.keys():
            settings[key] = defaultSettings[key]


# simple wrapper for default settings
def getDefaultSettings(prefix):
    prefix = os.path.basename(prefix)
    if prefix == '%s' % __LowerName__:
        return defIntSetings
    elif prefix == '%sd' % __LowerName__: 
        return defaultSettings


def get_path(pname='default', sufx='.conf'):
    # yield system-wide profile first
    yield os.path.join('/etc', __LowerName__ + sufx)
    # search for profiles other than system-wide one only if NOT running as
    # root (uid=0)
    if os.getuid() > 0:
        if settings.keys().count('profile'):
            pname = settings['profile']
        if os.path.dirname(pname):
            if os.path.basename(pname):
                yield pname
        else:
            if pname.endswith(sufx):
                pname = pname[:-len(sufx)]
            xdg_paths = list(load_config_paths(__LowerName__))
            xdg_paths.reverse()
            for directory in xdg_paths:
                yield os.path.join(directory, pname + sufx)


class wlogger():
    ''' Logger initializer

    This class initializes the logger for all other program's functions so
    *must* be called before requesting any customized logger.

    NOTE: Its modularity lets every log parameter be easily changed even if
          already started (such as for service version settings).
    '''

    def __init__(self, loglevel='info', logfile=None):
        if loglevel:
            numLvl = self.getILvl(loglevel)
        else:
            numLvl = None
        self.init_logs(numLvl, logfile)

    def getILvl(self, loglevel):
        numeric_level = getattr(logging, loglevel.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError("Invalid log level: %s" % loglevel)
        return numeric_level

    def init_logs(self, ilvl, flog=None, slog=None):
        self.logger = logging.getLogger(__LowerName__)
        self.logger.setLevel(logging.DEBUG)
        if ilvl:
            self.setStreamHandle(ilvl)
        if flog:
            self.setFileHandle(flog)

    def getFormat(self, handler):
        formatterCh = logging.Formatter(
            "[%(asctime)s][%(levelname)s - %(name)s] %(message)s",
            datefmt="%H:%M:%S")
        formatterFh = logging.Formatter(
            "[%(asctime)s][%(levelname)s - %(name)s] %(message)s",
            datefmt="%Y/%m/%d %H:%M:%S")
        if handler == 'ch':
            return formatterCh
        elif handler == 'fh':
            return formatterFh

    def setStreamHandle(self, ilvl):
        self.ch = logging.StreamHandler()
        self.ch.setLevel(ilvl)
        formatterCh = self.getFormat('ch')
        self.ch.setFormatter(formatterCh)
        self.logger.addHandler(self.ch)

    def setTemporaryHandler(self):
        import logging.handlers
        self.th = logging.handlers.MemoryHandler(2)
        formatterTh = self.getFormat('fh')
        self.th.setFormatter(formatterTh)
        self.logger.addHandler(self.th)

    def setFileHandle(self, flog):
        self.fh = logging.FileHandler(flog)
        self.fh.setLevel(logging.DEBUG)
        formatterFh = self.getFormat('fh')
        self.fh.setFormatter(formatterFh)
        self.logger.addHandler(self.fh)

    def changeLogLevel(self, loglevel):
        if loglevel:
            ilvl = self.getILvl(loglevel)
            self.ch.setLevel(ilvl)
        else:
            self.logger.removeHandler(self.ch)
            self.ch.close()

    def temporaryToPermanentSwitch(self):
        self.th.setTarget(self.fh)
        self.logger.removeHandler(self.th)
        self.th.close()
    
    def changeLogFile(self, flog):
        self.logger.removeHandler(self.fh)
        self.fh.close()
        if flog:
            self.setFileHandle(flog)


class serviceGetArgs():

    def __init__(self, argslist=None):
        self.argslist = argslist
        self.arguments = None

    def init_args(self):
        parser = argparse.ArgumentParser(
            description=(
                "A service that change screen's backlight according to "
                "ambient brightness through any v4l2 compatible camera"),
            prog="calised")
        parser.add_argument(
            '--version',
            action='version',
            version='%(pro)s %(ver)s' % dict(pro='%(prog)s', ver=__version__),
            help="display current version")
        # Service execution
        parser.add_argument(
            '-k', '--stop',
            action='store_true', default=None, dest='kill',
            help="terminate service")
        parser.add_argument(
            '--restart',
            action='store_true', default=None, dest='restart',
            help="restart service")
        parser.add_argument(
            '-e', '--pause',
            action='store_true', default=None, dest='pause',
            help="pause service")
        parser.add_argument(
            '-r', '--resume',
            action='store_true', default=None, dest='resume',
            help="resume service from \"pause\" state")
        parser.add_argument(
            '-c', '--capture',
            action='store_true', default=None, dest='capture',
            help="do a capture and set backlight accordingly")
        parser.add_argument(
            '--check',
            action='store_true', default=None, dest='check',
            help="check whether service is running or not")
        # Variable set
        parser.add_argument(
            '-p', '--profile',
            metavar='<profile>', dest='pname', default='default',
            help="specify either a valid profile name or path")
        parser.add_argument(
            '--location',
            metavar='<lat>:<lon>', dest='position', default=None,
            help="set geographical position expressed as float degrees")
        parser.add_argument(
            '--capture-number',
            metavar='<int>', dest='capnum', default=None,
            help=(
                "set number of captures per \"capture session\" (default: %d)"
                % defaultSettings['capnum']))
        parser.add_argument(
            '--capture-interval',
            metavar='<float>', dest='capint', default=None,
            help=(
                "set seconds between consecutive captures in a \"capture "
                "session\" (default: %f)" % defaultSettings['capint']))
        parser.add_argument(
            '--screen',
            action='store_true', default=None, dest='yscreen',
            help="enable screen-brightness compensation")
        parser.add_argument(
            '--no-screen',
            action='store_true', default=None, dest='nscreen',
            help="disable screen-brightness compensation")
        parser.add_argument(
            '--compensation-multiplier',
            metavar='<float>', dest='scrmul', default=None,
            help="screen-brightness compensation multiplier")
        parser.add_argument(
            '--weather',
            action='store_true', default=None, dest='yweather',
            help="enable weather internet lookup")
        parser.add_argument(
            '--no-weather',
            action='store_true', default=None, dest='nweather',
            help="disable weather internet lookup")
        parser.add_argument(
            '--geoip',
            action='store_true', default=None, dest='ygeoip',
            help="enable geoip internet lookup")
        parser.add_argument(
            '--no-geoip',
            action='store_true', default=None, dest='ngeoip',
            help="disable geoip internet lookup")
        # sleeptime-related
        parser.add_argument(
            '--twilight-mul',
            metavar='<float>', dest='dusksm', default=None,
            help=(
                "set the multiplier for dawn/sunset sleeptime (default: %f)"
                % defaultSettings['dusksm']))
        parser.add_argument(
            '--day-sleeptime',
            metavar='<float>', dest='dayst', default=None,
            help=(
                "set maximum seconds between captures during the day "
                "(default: 300)"))
        parser.add_argument(
            '--night-sleeptime',
            metavar='<float>', dest='nightst', default=None,
            help=(
                "set seconds between captures at night; 0 means no captures "
                "(default)"))
        # Logging
        parser.add_argument(
            '--loglevel',
            metavar='<level>', dest='loglevel', default=None,
            help="log level: error, warning, info (default) or debug")
        parser.add_argument(
            '--logfile',
            metavar='<path>', dest='logfile', default=None,
            help=(
                "log output file (tempfile inside calise tempdir if not "
                "specified)"))
        parser.add_argument(
            '-d', '--dump',
            action='store_true', default=None, dest='dump',
            help="dump last capture data")
        parser.add_argument(
            '-a', '--dump-all',
            action='store_true', default=None, dest='dumpall',
            help="dump all captured data from program start")
        parser.add_argument(
            '--dump-settings',
            action='store_true', default=None, dest='dumpsettings',
            help="dump current execution's settings")
        self.arguments = vars(parser.parse_args(self.argslist))
        self.parser = parser

    def parse_settings(self):
        ''' Settings parser

        NOTE: Service execution related arguments won't be processed there
              since service communication is done through command existence
              in args variable (actual command content isn't processed).
              At the end of this function all service commands with value
              None are stripped so that only given commands remain.

                eg. args = {'kill': 0, 'dump': "zaczac"} -> kill, dump
                eg. args = {'kill': False, 'dump': 1}    -> kill, dump
        '''
        global settings
        args = self.arguments
        # Settings related arguments
        if args['pname']:
            settings['profile'] = args['pname']
        if args['position']:
            lat, lon = [float(x) for x in args['position'].split(':')]
            settings['latitude'], settings['longitude'] = lat, lon
            args['latitude'], args['longitude'] = lat, lon
            del args['position']
        if args['capnum']:
            settings['capnum'] = int(args['capnum'])
        if args['capint']:
            settings['capint'] = float(args['capint'])
        if args['yscreen']:
            settings['screen'] = True
        elif args['nscreen']:
            settings['screen'] = False
        if args['scrmul']:
            settings['scrmul'] = args['scrmul']
        if args['yweather']:
            settings['weather'] = True
        elif args['nweather']:
            settings['weather'] = False
        if args['ygeoip']:
            settings['geoip'] = True
        elif args['ngeoip']:
            settings['geoip'] = False
        # sleeptime-related arguments
        if args['dusksm']:
            settings['dusksm'] = float(args['dusksm'])
        if args['dayst']:
            settings['dayst'] = float(args['dayst'])
        if args['nightst']:
            settings['nightst'] = float(args['nightst'])
        # Logging related arguments
        if args['loglevel']:
            settings['loglevel'] = args['loglevel']
        if args['logfile']:
            settings['logfile'] = args['logfile']
        # Arguments variable post-processing
        # every service execution's related var is added to $serviceArgs
        serviceArgs = {}  # dictionary object
        queryArgs = {}
        execArgs = {}
        for key in args.keys():
            if args[key] is not None:
                if key in serviceCommands:
                    serviceArgs[key] = args[key]
                    if key in queryCommands:
                        queryArgs[key] = args[key]
                    if key in execCommands:
                        execArgs[key] = args[key]
            else:
                del args[key]
        # arguments export
        self.args = args
        self.serviceArgs = serviceArgs
        self.queryArgs = queryArgs
        self.execArgs = execArgs


class coreGetArgs():

    def __init__(self, argslist=None):
        self.argslist = argslist
        self.arguments = None

    def init_args(self):
        parser = argparse.ArgumentParser(
            description=(
                "A program that change screen's backlight according to "
                "ambient brightness through any v4l2 compatible camera"),
            prog="calised")
        parser.add_argument(
            '--version',
            action='version',
            version='%(pro)s %(ver)s' % dict(pro='%(prog)s', ver=__version__),
            help="display current version")
        parser.add_argument(
            '--calibrate', '--configure',
            action='store_true', default=None, dest='configure',
            help="launch the calibration")
        parser.add_argument(
            '-p', '--profile',
            metavar='<profile>', dest='pname', default='default',
            help="profile name or path")
        parser.add_argument(
            '--path',
            metavar='<path>', dest='path', default=None,
            help="sysfs brightness path")
        parser.add_argument(
            '--capture-interval', '--gap',
            metavar='<float>', dest='gap', default=None,
            help=(
                "seconds between consecutive captures (default: %f)"
                % defIntSetings['gap']))
        parser.add_argument(
            '--verbose',
            action='store_true', default=None, dest='yverbose',
            help="enable verbose output")
        parser.add_argument(
            '--no-verbose',
            action='store_true', default=None, dest='nverbose',
            help="disable verbose output")
        parser.add_argument(
            '--gui',
            action='store_true', default=None, dest='ygui',
            help="enable GUI")
        parser.add_argument(
            '--no-gui',
            action='store_true', default=None, dest='ngui',
            help="disable GUI (run cli-interface)")
        parser.add_argument(
            '--screen',
            action='store_true', default=None, dest='yscreen',
            help="enable screen-brightness compensation")
        parser.add_argument(
            '--no-screen',
            action='store_true', default=None, dest='nscreen',
            help="disable screen-brightness compensation")
        parser.add_argument(
            '--compensation-multiplier',
            metavar='<float>', dest='scrmul', default=None,
            help="screen-brightness compensation multiplier")
        parser.add_argument(
            '--auto',
            action='store_true', default=None, dest='yauto',
            help="enable automatic backlight level change")
        parser.add_argument(
            '--no-auto',
            action='store_true', default=None, dest='nauto',
            help="disable automatic backlight level change")
        parser.add_argument(
            '--record',
            action='store_true', default=None, dest='yrecord',
            help="enable data record")
        parser.add_argument(
            '--no-record',
            action='store_true', default=None, dest='nrecord',
            help="disable data record")
        parser.add_argument(
            '--recordfile',
            metavar='<path>', dest='recfile', default=None,
            help=(
                "record output file (cli-interface will export recorded "
                "data there, gui-interface will let you choose)"))
        parser.add_argument(
            '--logfile',
            metavar='<path>', dest='logfile', default=None,
            help=(
                "log output file (none if not set)"))
        self.arguments = vars(parser.parse_args(self.argslist))
        self.parser = parser

    # Settings parser from cli-arguments
    def parse_settings(self):
        global settings
        args = self.arguments
        # Settings related arguments
        if args['configure']:
            settings['configure'] = args['configure']
        if args['path']:
            settings['path'] = args['path']
        if args['pname']:
            settings['profile'] = args['pname']
        if args['gap']:
            settings['gap'] = float(args['gap'])
        if args['yverbose']:
            settings['verbose'] = True
        elif args['nverbose']:
            settings['verbose'] = False
        if args['ygui']:
            settings['gui'] = True
        elif args['ngui']:
            settings['gui'] = False
        if args['yscreen']:
            settings['screen'] = True
        elif args['nscreen']:
            settings['screen'] = False
        if args['scrmul']:
            settings['scrmul'] = args['scrmul']
        if args['yauto']:
            settings['auto'] = True
        elif args['nauto']:
            settings['auto'] = False
        # Logging related arguments
        if args['yrecord']:
            settings['record'] = True
        elif args['nrecord']:
            settings['record'] = False
        if args['recfile']:
            settings['recfile'] = args['recfile']
        if args['logfile']:
            settings['logfile'] = args['logfile']
        # Arguments variable post-processing
        ''' put here any post process to be applied to arguments '''


class profiler():

    # options syntax:
    #   Group: {option: (data_type, self.settings_key)}
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
            'compensation-multiplier': (float, 'scrmul'),
            'auto': (bool, 'auto'),
            'record': (bool, 'record'),
            'recordfile': (str, 'recfile'),
            'gui': (bool, 'gui'),
            'verbose': (bool, 'verbose'),
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
