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

import time
import datetime
import ephem
import re
import urllib
import logging

from calise.infos import __LowerName__


logger = logging.getLogger(".".join([__LowerName__, 'ephem']))


def getDst(curTime=None):
    ''' Daylight Saving Time (DST) shift

    Get current (if any) dst shift for local timezone.
    This is needed since all pyephem times are based upon GMT *without* any
    dst setting.

    '''
    zg = time.localtime(curTime)
    wg = time.gmtime(curTime)
    dst_shift = (
        (wg.tm_hour * 60 + wg.tm_min) * 60 -
        (zg.tm_hour * 60 + zg.tm_min) * 60 -
        time.timezone)
    if dst_shift > 12 * 3600:
        dst_shift -= 24 * 3600
    elif dst_shift < -12 * 3600:
        dst_shift += 24 * 3600
    return dst_shift


def getSun(latitude, longitude, curTime=None):
    ''' Sun-related informations

    Given lat/long this function returns rise_time and setting_time in
    epoch and for how long (in sec) will the sunlight be "unstable" since
    dawn/sunset.

    NOTE: error exception ephem.NeverUpError means that the sun never reaches
          chosen degrees above the horizon.
    '''
    if curTime is None:
        curTime = time.time()
    obs = ephem.Observer()
    obs.lat = str(latitude)
    obs.long = str(longitude)
    sun = ephem.Sun()
    dst = getDst(curTime)
    # pyEphem works on utc time. This requires a forth conversion since every
    # epoch obtained will be shifted by %timezone%
    obs.date = datetime.date.fromtimestamp(curTime)
    try:
        # considering civil twilight as rise/set time
        obs.horizon = '-6'
        # civil rise and set times setting and epoch conversion
        rise_time = obs.next_rising(sun).datetime()
        rise_epoch = int(rise_time.strftime('%s')) - time.timezone - dst
        set_time = obs.next_setting(sun).datetime()
        set_epoch = int(set_time.strftime('%s')) - time.timezone - dst
        # increase horizon to calculate for how long the sunlight will rapidly
        # change intensity. 15 is arbitrary and tested only for 46.04N latitude
        obs.horizon = '15'
        try:
            set_dur = obs.next_setting(sun).datetime()
            set_dur = (
                set_epoch - int(set_dur.strftime('%s')) + 
                time.timezone + dst)
            rise_dur = obs.next_rising(sun).datetime()
            rise_dur = (
                int(rise_dur.strftime('%s')) - rise_epoch -
                time.timezone - dst)
            # TODO: the 4 rows below are a crappy workaround, need to be fixed
            if set_dur < 0:
                set_dur += 24 * 60 * 60
            if rise_dur < 0:
                rise_dur += 24 * 60 * 60
        except ephem.NeverUpError:
            set_dur = set_epoch - rise_epoch
            rise_dur = set_epoch - rise_epoch
    except ephem.NeverUpError:
        rise_epoch = False
        set_epoch = True
        rise_dur = 0
        set_dur = 0
    except ephem.AlwaysUpError:
        obs.horizon = '15'
        try:
            # 86400 below is the number of seconds of a day
            set_epoch = int(datetime.date.today().strftime('%s')) + 86400
            set_dur = (
                set_epoch -
                int(obs.next_setting(sun).datetime().strftime('%s')) +
                time.timezone + dst)
            rise_epoch = int(datetime.date.today().strftime('%s'))
            rise_dur = (
                int(obs.next_rising(sun).datetime().strftime('%s')) -
                rise_epoch -
                time.timezone - dst)
        except ephem.AlwaysUpError:
            rise_epoch = True
            set_epoch = False
            rise_dur = 0
            set_dur = 0
    return rise_epoch, set_epoch, rise_dur, set_dur


def url_parse(lat, lon, parser='wunderground'):
    ''' Weather apis parser

    Takes api name and, if present, through that api retrives current weather
    informations.
    If api is not listed or there's no internet connection, returns None.

    '''
    if parser == 'wunderground':
        api = 'api.wunderground.com/auto/wui/geo/WXCurrentObXML/index.xml'
        params = urllib.urlencode({'query': '%.4f,%.4f' % (lat, lon)})
        prog = re.compile((
            ".*?<current_observation>"
            ".*?<weather>([A-Z a-z]*?)</weather>"
            ".*?</current_observation>"), re.DOTALL)
    elif parser == 'google':
        api = 'www.google.com/ig/api'
        params = urllib.urlencode({
            'hl': 'en',
            'weather': ',,,%d,%d' % (lat * 1000000, lon * 1000000)})
        prog = re.compile((
            ".*?<\?xml.*?\?>.*?<current_conditions>"
            ".*?<condition data=\"([A-Z a-z]*?)\"/>"
            ".*?</xml_api_reply>"), re.DOTALL)
    try:
        wur = urllib.urlopen('https://%s?%s' % (api, params))
    # IOError is raised if there's no internet connection
    except IOError:
        return None
    cm = prog.match(wur.read())
    # Some apis return a blank string instead of None with the second "if"
    # condition the parser is aware of that
    if cm is not None and len(cm.group(1).split()) > 0:
        return cm.group(1)
    else:
        return None


def get_daytime_mul(lat, lon):
    ''' Weather informations

    Asks the apis defined with url_parse function for weather informations and
    transforms them into a multiplier (from defined min to defined max).
    If a "weather state" is not indexed, then returns (min+max)/3.

    '''
    for api in ('wunderground', 'google'):
        ws = url_parse(lat, lon, api)
        if ws is not None:
            break
    # multiplier minimum and maximum
    minimum = 0.2
    maximum = 1.0
    step = (maximum - minimum) / 7.0
    fmul = (minimum + maximum) / 3.0
    if ws is not None:
        # daytime multiplier based on weather conditions (from 1.0 to 0.2)
        weather_mul = {
            # Commons
            'clear': minimum + step * 7,               # < 1/8 sky coverage
            'mostly sunny': minimum + step * 6,        # 1/8 to 3/8 coverage
            'partly sunny': minimum + step * 5,        # 3/8 to 4/8 coverage
            'partly cloudy': minimum + step * 4,       # 4/8 to 5/8 coverage
            'mostly cloudy': minimum + step * 3,       # 5/8 to 6/8 coverage
            'cloudy': minimum + step * 2,              # 6/8 to 7/8 coverage
            'overcast': minimum + step * 1,            # 8/8 coverage
            # Others
            'scattered clouds': minimum + step * 5.5,  # 10% to 50% coverage
            'chance of rain': minimum + step * 4,
            'light rain': minimum + step * 3,
            'light thunderstorm rain': minimum + step * 0.5,
            'rain': minimum + step * 1.5,
            'chance of storm': minimum + step * 2.5,
            'light storm': minimum + step * 1,
            'storm': minimum + step * 0,
            'thunderstorm': minimum + step * 0,
            'chance of snow': minimum + step * 4.5,
            'light snow': minimum + step * 2,
            'snow': minimum + step * 1,
            'Mist': minimum + step * 5,
            'Fog': minimum + step * 3,
            }
        try:
            fmul = weather_mul[str(ws).lower()]
        except KeyError:
            pass
        logger.debug(
            "weather condition found: \"%s\", mul set to %.3f" % (ws, fmul))
    else:
        logger.warning("weather condition not found, mul set to %.3f" % fmul)
    return fmul


def get_geo():
    geo = None
    api = 'geoiplookup.wikimedia.org'
    try:
        gur = urllib.urlopen('https://%s' % api)
    except IOError:
        return None
    try:
        geo = eval(gur.read().replace("Geo = ", ""))
        geo['lat'] = float(geo['lat'])
        geo['lon'] = float(geo['lon'])
        logger.debug(
            "geoip lookup successed: \"%s\" (%.3f,%.3f)"
            % (geo['city'], geo['lat'], geo['lon']))
    except SyntaxError:
        logger.warning("geoip lookup failed")
    return geo
