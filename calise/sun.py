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


def convertPyEphemToEpoch(timeString):
    ''' GMT string time to seconds since epoch converter
    
    Given a "YYYY/MM/DD HH:MM:SS" GMT time a time.tz struct is created and then
    converted in localtime (wrong) epoch, corrected by timezone and dst shifts.
    
    NOTE: PyEphem lib works with GMT times but since converting between GMT and
          localtime requires calendar lib (and some further coding) and calise
          won't work behind the ephem I preferred ephem times over GMT.
    '''
    timeEpoch = (
        time.mktime(time.strptime(str(timeString), "%Y/%m/%d %H:%M:%S")) - 
        time.altzone)
    return timeEpoch


def getSun(latitude, longitude, timestamp=None):
    ''' Returns Sun rising and setting times and durations
    
    Given latitude and longitude, returns rising and setting epoch localtimes
    and the time the Sun spends from -6 to 15 (and 15 to -6 respectively) above
    the horizon.
    
    NOTE: recurrent integer "86400" is the number of seconds in a day.
    
    TODO: understand why obs.date increases after next_something functions...
          re-setting variable every pyEphem query sucks.
    '''
    if timestamp == None:
        timestamp = time.time()
    # PyEphem observer setting
    obs = ephem.Observer()
    obs.lat = str(latitude)
    obs.long = str(longitude)
    sun = ephem.Sun()
    obs.date = datetime.date.fromtimestamp(timestamp)
    # 00:00 of the day after %timestamp's one
    epochRefer = (
        float(datetime.date.fromtimestamp(timestamp).strftime("%s")) + 86400)
    # considering civil twilight as rise/set time
    obs.horizon = '-6'
    try:
        riseStartEpoch = convertPyEphemToEpoch(obs.next_rising(sun))
        obs.date = datetime.date.fromtimestamp(timestamp)
        setEndEpoch = convertPyEphemToEpoch(obs.next_setting(sun))
        # increase horizon to calculate for how long the sunlight will rapidly
        # change intensity. 15 is arbitrary and tested only for 46.04N latitude
        obs.horizon = '15'
        try:
            riseEndEpoch = convertPyEphemToEpoch(obs.next_rising(sun))
            obs.date = datetime.date.fromtimestamp(timestamp)
            setStartEpoch = convertPyEphemToEpoch(obs.next_setting(sun))
            riseDuration = riseEndEpoch - riseStartEpoch
            setDuration = setEndEpoch - setStartEpoch
        except ephem.NeverUpError:
            # Sun rises but never reaches 15 grades above the horizon and so
            # the whole day (from rise time to set time) will be a
            # rising/setting phase
            setDuration = (setEndEpoch - riseStartEpoch) / 2.0
            riseDuration = (setEndEpoch - riseStartEpoch) / 2.0
    except ephem.NeverUpError:
        # Sun never rises and so rising and setting times are set to 00:00 of
        # %timestamp's day, meaning that rising, daylight and setting times
        # will be set to 0 sec
        riseStartEpoch = epochRefer - 86400
        setEndEpoch = epochRefer - 86400
        riseDuration = 0
        setDuration = 0
    except ephem.AlwaysUpError:
        # Sun will always be above the horizon (-6) and so rise is set to 00:00
        # of %timestamp's day and set to 00:00 of the day after %timestamp's
        # one, meaning there is no "night".
        obs.horizon = '15'
        try:
            riseStartEpoch = epochRefer - 86400
            riseEndEpoch = convertPyEphemToEpoch(obs.next_rising(sun))
            obs.date = datetime.date.fromtimestamp(timestamp)
            setEndEpoch = epochRefer
            setStartEpoch = convertPyEphemToEpoch(obs.next_setting(sun))
             # Compute durations
            riseDuration = riseEndEpoch - riseStartEpoch
            setDuration = setEndEpoch - setStartEpoch
        except ephem.AlwaysUpError:
            riseStartEpoch = epochRefer - 86400
            setEndEpoch = epochRefer
            riseDuration = 0
            setDuration = 0
        except ephem.NeverUpError:
            riseStartEpoch = epochRefer - 86400
            setEndEpoch = epochRefer
            riseDuration = 86400 / 2
            setDuration = 86400 / 2
    return riseStartEpoch, setEndEpoch, riseDuration, setDuration


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
