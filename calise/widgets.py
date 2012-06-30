# -*- coding: utf-8 -*-
#    Copyright (C)   2011   Nicolo' Barbon
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

import sys
from PyQt4 import QtGui, QtCore


'''Dynamic and Interactive custom progress bar that fits backlight steps
'''
class BacklightWidget(QtGui.QWidget):

    def __init__(self, pal):
        super(BacklightWidget, self).__init__()
        self.palette = pal # color palette
        self.initData()
        self.initUI()

    def initData(self):
        self.bar = 0 # average brightness percentage (float)
        self.cur = 0 # current backlight step (int)
        self.tgt = 0 # suggested backlight step (int)
        self.sps = None # number of backlight steps (int)
        self.MousePressed = False
        self.Paused = False

    def initUI(self):
        self.setMinimumSize(1, 30)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape(2)))

    # paint event override:
    # creates a QPainter object, draws and then terminates that object
    def paintEvent(self, e):
        qp = QtGui.QPainter()
        qp.begin(self)
        self.drawBacklightBar(qp,105.0)
        qp.end()

    # draw bar function: fill, stepBars, baseScale
    def drawBacklightBar(self, qp, bs=100.0):

        size = self.size()
        w = size.width()
        h = size.height()

        # draw fill
        till = int( round((w / bs) * self.bar, 0) )
        qp.setOpacity(0.5)
        if self.Paused is True:
            qp.setPen(self.palette.shadow().color())
            qp.setBrush(self.palette.shadow().color())
            qp.drawRect(0, 0, till, h)
        elif self.bar > 60:
            qp.setPen(QtGui.QColor(252,233,79))
            qp.setBrush(QtGui.QColor(252,233,79))
            qp.drawRect(0, 0, till, h)
        elif self.bar > 40 and self.bar <= 60:
            qp.setPen(QtGui.QColor(245,121,0))
            qp.setBrush(QtGui.QColor(245,121,0))
            qp.drawRect(0, 0, till, h)
        else:
            qp.setPen(QtGui.QColor(114,159,207))
            qp.setBrush(QtGui.QColor(114,159,207))
            qp.drawRect(0, 0, till, h)
        qp.setOpacity(1.0)
        pen = QtGui.QPen(
            self.palette.shadow().color(), 1, QtCore.Qt.SolidLine)
        qp.setPen(pen)
        qp.setBrush(QtCore.Qt.NoBrush)
        qp.drawRect(0, 0, w-1, h-1)

        if self.sps is None: return
        steps = self.sps
        self.pxs = w / (steps + .5)

        # draw step bars
        pos = int(round(self.cur * self.pxs, 0))
        qp.drawLine(pos, 1, pos, h)
        qp.setOpacity(0.33)
        pos = int(round(self.tgt * self.pxs, 0))
        qp.drawLine(pos, 1, pos, h)
        qp.setOpacity(1.00)

        # draw scale
        if int(round(steps, 0)) < 21:
            pen = QtGui.QPen(
                self.palette.buttonText().color(), 1, QtCore.Qt.SolidLine)
            qp.setPen(pen)
            pos = int(round(1 * self.pxs - self.pxs / 2.0, 0))
            qp.drawLine(pos, 1, pos, 6)
            for i in range(1, steps):
                pos = int(round(i * self.pxs, 0))
                pon = int(round(i * self.pxs + self.pxs / 2, 0))
                qp.drawLine(pos, 1, pos, 10)
                qp.drawLine(pon, 1, pon, 6)
            pos = int(round((i + 1) * self.pxs, 0))
            qp.drawLine(pos, 1, pos, 10)
            self.setMinimumSize(10 * steps, 30)

    # dummy mousePress override, initializes mouseEvent
    def mousePressEvent(self, event):
        if event.button() != 1: return
        self.MousePressed = True

    # if mouseEvent inizialized: pause trough, convert click
    # position to backlight step, set backlight and finally update Wideget
    def mouseReleaseEvent(self, event):
        if event.button() != 1: return
        if self.MousePressed == True:
            self.MousePressed = False
        steps = self.sps
        pxs = self.width() / (steps + .5)
        cur = int(round(event.x() / pxs, 0))
        if (
            event.x() < 0 or event.x() > self.width() or
            event.y() < 0 or event.y() > self.height()
        ): return
        if cur < 1: cur = 1
        elif cur > steps: cur = steps
        QtCore.QObject.emit( self, QtCore.SIGNAL('bbwBarClicked(int)'), cur )

    def enPause(self,boolean):
        self.Paused = boolean


class AvdancedInfo(QtGui.QWidget):

    def __init__(self):
        super(AvdancedInfo, self).__init__()
        self.initUI()

    def initUI(self):

        # First part of the Description entries, relative to single captures
        self.fForm = QtGui.QFormLayout()
        self.fForm.setVerticalSpacing(0)
        self.abLabel = QtGui.QLabel()
        self.abLabel.setAlignment(QtCore.Qt.AlignRight)
        self.fForm.addRow(
            QtCore.QString.fromUtf8(_('Ambient brightness')), self.abLabel )
        self.sbLabel = QtGui.QLabel()
        self.sbLabel.setAlignment(QtCore.Qt.AlignRight)
        self.fForm.addRow(
            QtCore.QString.fromUtf8(_('Screen brightness')), self.sbLabel )
        self.bcLabel = QtGui.QLabel()
        self.bcLabel.setAlignment(QtCore.Qt.AlignRight)
        self.fForm.addRow(
            QtCore.QString.fromUtf8(_('Brightness correction')), self.bcLabel )
        self.bpLabel = QtGui.QLabel()
        self.bpLabel.setAlignment(QtCore.Qt.AlignRight)
        self.fForm.addRow(
            QtCore.QString.fromUtf8(_('Brightness percentage')), self.bpLabel )

        # Second (and last) part of the Description entries, relative to an
        # average of values
        self.sForm = QtGui.QFormLayout()
        self.sForm.setVerticalSpacing(0)
        self.apLabel = QtGui.QLabel()
        self.apLabel.setAlignment(QtCore.Qt.AlignRight)
        self.sForm.addRow(
            QtCore.QString.fromUtf8(_('Average percentage')), self.apLabel )
        self.avLabel = QtGui.QLabel()
        self.avLabel.setAlignment(QtCore.Qt.AlignRight)
        self.sForm.addRow(
            QtCore.QString.fromUtf8(_('Averaged values')), self.avLabel )
        self.cbLabel = QtGui.QLabel()
        self.cbLabel.setAlignment(QtCore.Qt.AlignRight)
        self.sForm.addRow(
            QtCore.QString.fromUtf8(_('Current backlight')), self.cbLabel )
        self.ssLabel = QtGui.QLabel()
        self.ssLabel.setAlignment(QtCore.Qt.AlignRight)
        self.sForm.addRow(
            QtCore.QString.fromUtf8(_('Suggested backlight')), self.ssLabel )
        self.ltLabel = QtGui.QLabel()
        self.ltLabel.setAlignment(QtCore.Qt.AlignRight)
        self.sForm.addRow(
            QtCore.QString.fromUtf8(_('Lock Expiry')), self.ltLabel )

        # Group boxes
        self.fGroup = QtGui.QGroupBox(
            QtCore.QString.fromUtf8(_( 'Capture Data' )))
        self.sGroup = QtGui.QGroupBox(
            QtCore.QString.fromUtf8(_( 'Averaging Data' )))
        self.fGroup.setLayout(self.fForm)
        self.sGroup.setLayout(self.sForm)

        # Layout Boxes
        self.VBox = QtGui.QVBoxLayout()
        self.VBox.addWidget(self.fGroup)
        self.VBox.addWidget(self.sGroup)
        self.setLayout(self.VBox)
