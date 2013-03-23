#!/usr/bin/env python2


import os
import sys
import time

from calise.calibration.functions import *
from calise.console import getTerminalSize
from calise.getkey import _Getch
getch = _Getch()


DEFAULT_STEP = 200.0


def computeSteps(maxValue, minValue):
    """ Compute optimal backlight level changing steps """
    step = (maxValue - minValue) / DEFAULT_STEP
    histep = int(round(((maxValue - minValue) / DEFAULT_STEP) * 10 + .49, 0))
    if step < 1:
        step = 1
    return step, histep


def defineVars(interface):
    """ Define target interface's properties 
    
    Generate a dictionary containing both min/max value available and computed
    change step and fast-change step (got with computeSteps())
    
    """
    minValue = getMinimumLevel(os.path.join(interface, 'brightness'))
    maxValue = readInterfaceData(os.path.join(interface, 'max_brightness'))
    baseStep, highStesp = computeSteps(maxValue, minValue)
    interfaceProperties = {
        'min': minValue,
        'max': maxValue,
        'base-step': baseStep,
        'high-step': highStesp,
    }
    return interfaceProperties


def getArrowPressed():
    """ Get which arrow has been pressed
    
    Since arrow keys (and other keyboard inputs) are complex and won't last
    after 1st byte grabbed by getch(), this function tries to recognize inputs
    and eventually except/stop if they're not expected ones (such as arrow
    keys)
    
    NOTE: Known Issue: 'Escape' and 'Cancel' (and I bet also other tons) keys
          bug that function
          
    TODO: Get a *real* any-bit key recognition
    
    """
    ch = []
    arrowKey = None
    # crappy way to get complex key recognition (works only with arrow keys)
    for x in range(3):
        ch.append(getch())
        if x == 0 and ch[0] in ['Q', 'q', '\r', '\n']:
            arrowKey = 'quit'
            break
        elif x == 0 and not ch[0] == '\x1b':
            sys.stderr.write('test input error message\n')
            break
        elif x == 1 and not ch[1] == '[':
            sys.stderr.write('test input error message\n')
        elif x == 2 and not ch[2] in 'ABCD':
            sys.stderr.write('test input error message\n')
    if len(ch) == 3:
        if ch[2] == 'A':
            arrowKey = 'up'
        elif ch[2] == 'B':
            arrowKey = 'down'
        elif ch[2] == 'C':
            arrowKey = 'right'
        elif ch[2] == 'D':
            arrowKey = 'left'
    return arrowKey


def drawValueProgress(value, valMin, valMax):
    """ Fancy current-step-indicator ^_^
    
    Dinamic and somehow fancy print layout to show current backlight step.
    
    """
    termWidth = getTerminalSize()[0]
    text = len(str(valMax)) * 2 + 1
    progressStep = termWidth - text - 1
    progress = (valMax - valMin) / float(progressStep)
    sys.stdout.write(' ' * termWidth + '\r')
    sys.stdout.write(
        "%s%d/%d " % 
        ((len(str(valMax)) - len(str(value))) * ' ', value, valMax)
    )
    for k in range(int(round(value/progress))):
        sys.stdout.write("|")
    sys.stdout.write('\r')
    sys.stdout.flush()


def setBrightness(interface):
    """ Backlight adjusting function
    
    Given %interface int value, will be increased/decreased when getch()
    function grabs a 'RIGHT' or 'LEFT' keypress (one by one or by a
    proportional amount if 'UP' or 'DOWN' are pressed instead).
    
    """
    curValue = readInterfaceData(os.path.join(interface, 'brightness'))
    newValue = curValue
    curProperties = defineVars(interface)
    drawValueProgress(curValue, curProperties['min'], curProperties['max'])
    while True:
        key = getArrowPressed()
        if key == 'up':
            newValue = curValue + curProperties['high-step']
        elif key == 'down':
            newValue = curValue - curProperties['high-step']
        elif key == 'right':
            newValue = curValue + curProperties['base-step']
        elif key == 'left':
            newValue = curValue - curProperties['base-step']
        elif key == 'quit':
            print ''
            break
        if newValue > curProperties['max']:
            newValue = curProperties['max']
        elif newValue < curProperties['min']:
            newValue = curProperties['min']
        if newValue != curValue:
            writeInterfaceData(os.path.join(interface, 'brightness'), newValue)
            curValue = newValue
            drawValueProgress(newValue, curProperties['min'], curProperties['max'])
    return newValue








def instructionsFormat(instruction, tip=""):
    """ Instruction print
    
    Instruction part contains the instruction itself and any handful note
    and/or furter explanation related, the tip part instead contains anything
    with *no* instruction understanding purposes (just a tip)

    """
    print ">>> " + instruction  + '\n'
    if tip:
        print "TIP: " + tip + '\n'


if __name__ == '__main__':
    #print defineVars('/sys/class/backlight/psb-bl/')
    #setBrightness('/sys/class/backlight/psb-bl/')
    #setBrightness(sys.argv[1])
    import time
    import os
    import sys
    tcv = readInterfaceData(bfile)
    for x in range(2):
        writeInterfaceData(bfile, getMinimumLevel(bfile))
        time.sleep(.33)
        writeInterfaceData(bfile, readInterfaceData(
            os.path.join(os.path.dirname(bfile), 'max_brightness')
        ))
        time.sleep(.33)
    writeInterfaceData(bfile, tcv)


"""
    msgStrIns = (
        "Adjust screen backlight with arrow keys. Left and right will " +
        "decrease and/or increase current backlight value by a low amount, " +
        "down and up will do that by a larger amount.")
    msgStrTip = (
        "try to set ambient brghtness as brightness as possible for best " +
        "results.")
    instructionsFormat(msgStrIns, msgStrTip)
"""