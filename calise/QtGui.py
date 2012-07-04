# -*- coding: utf-8 -*-
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
import time
import signal
from PyQt4 import QtGui, QtCore

from calise.capture import imaging
from calise.system import execution
from calise.ExecThreads import mainLoop, _locker
from calise import infos
from calise.widgets import AvdancedInfo, BacklightWidget


app = None       # QApplication
palette = None   # palette object corresponding to system palette (from theme)
arguments = None # dictionary with arguments (first data) returned by thread
procData = None  # dictionary with current thread data, updated every capture

'''main window's main widget
Everything appears on MainWindow must be declared there and added to MainVbox
'''
class MainWid(QtGui.QWidget):

    def __init__(self):
        super(MainWid, self).__init__()
        self.initUI()

    def initUI(self):

        # vars and high level widgets declaration
        self.AddIn = AvdancedInfo()
        self.bbw = BacklightWidget(palette)
        self.com = LineParser() # QThread executer and parser

        # low level widgets
        self.AddInBtn = QtGui.QPushButton(
        QtGui.QIcon.fromTheme('text-x-generic'), '' )
        self.AddInBtn.setCheckable(True)
        self.PauseBtn = QtGui.QPushButton(
        QtGui.QIcon.fromTheme('media-playback-pause'), '' )
        self.PauseBtn.setCheckable(True)
        self.RecordBtn = QtGui.QPushButton(
        QtGui.QIcon.fromTheme('media-record'), '' )
        self.RecordBtn.setCheckable(True)
        self.ExportBtn = QtGui.QPushButton(
        QtGui.QIcon.fromTheme('media-floppy'), '' )
        self.AddInBtn.setFixedSize(34,34)
        self.PauseBtn.setFixedSize(34,34)
        self.RecordBtn.setFixedSize(34,34)
        self.ExportBtn.setFixedSize(34,34)

        # signal handling
        self.connect(
            self.com, QtCore.SIGNAL('valueChanged()'), self.changeValue )
        self.connect(
            self.bbw, QtCore.SIGNAL('bbwBarClicked(int)'), self.bbwBarAction )
        self.PauseBtn.toggled.connect(self.OnPause)
        self.RecordBtn.toggled.connect(self.OnRec)
        self.ExportBtn.clicked.connect(self.OnExport)
        self.com.start()

        # set tooltips
        self.PauseBtn.setToolTip(QtCore.QString.fromUtf8(_(
            'Pause execution and unload the camera'
        )))
        self.RecordBtn.setToolTip(QtCore.QString.fromUtf8(_(
            'Start/Stop recording session\n'
            'each session is appended to previous one'
        )))
        self.ExportBtn.setToolTip(QtCore.QString.fromUtf8(_(
            'Export recorded data'
        )))
        self.AddInBtn.setToolTip(QtCore.QString.fromUtf8(_(
            'Display detailed informations'
        )))
        self.bbw.setToolTip(QtCore.QString.fromUtf8(_(
            'Interactive backlight scale\n'
            'click to pause execution and set backlight step\n'
            'corresponding to click position'
        )))

        # layout settings
        # backlight bar is conatined in a Horizonal box to create some margin,
        # then that HBox is contained in a vertical box to vertucally center.
        # this avoids the widget to vertically resize (since it will be ugly)
        barHBox = QtGui.QHBoxLayout()
        barHBox.setContentsMargins(2,1,2,1)
        barHBox.addWidget(self.bbw)
        barVBox = QtGui.QVBoxLayout()
        barVBox.addLayout(barHBox)
        # MainHbox contains every widget in the lower part of the window
        MainHbox = QtGui.QHBoxLayout()
        MainHbox.setSpacing(2)
        MainHbox.addWidget(self.PauseBtn,0)
        MainHbox.addLayout(barVBox)
        MainHbox.addWidget(self.AddInBtn,0)
        MainHbox.addWidget(self.RecordBtn,0)
        MainHbox.addWidget(self.ExportBtn,0)
        MainHbox.setMargin(0)
        # MainVbox is last real Main layout box
        MainVbox = QtGui.QVBoxLayout()
        MainVbox.setSpacing(0)
        MainVbox.addWidget(self.AddIn)
        MainVbox.addLayout(MainHbox)
        MainVbox.setContentsMargins(1,0,1,1)
        self.AddIn.hide()
        self.RecordBtn.hide()
        self.ExportBtn.hide()
        self.setLayout(MainVbox)

    def OnPause(self,boolean):
        if boolean:
            self.com.td.sig = 'pause'
            self.bbw.enPause(True)
            self.bbw.repaint()
        else:
            self.com.td.sig = 'resume'
            self.bbw.enPause(False)
        QtCore.QObject.emit(
                self, QtCore.SIGNAL('pauseToggled(bool)'), boolean )

    def OnRec(self,boolean):
        self.com.td.args.logdata = not self.com.td.args.logdata

    # sends CUSTOM2 signal to export recorded data to /tmp/whatever.csv,
    # then copies that csv file content to a user's specified (through dialog)
    # location
    def OnExport(self):
        filename = QtGui.QFileDialog.getSaveFileName(
            self, 'Open file',os.getenv('HOME'))
        if filename == QtCore.QString(''):
            return
        self.com.td.ExpPath = filename
        self.com.td.sig = 'export'

    def changeValue(self):
        if self.bbw.isVisible(): self.updateBacklightMeter()
        if self.AddIn.isVisible() and procData != None: self.updateAddData()

    # refreshes backlight bar meter values and repaints
    def updateBacklightMeter(self):
        if arguments: self.bbw.sps = arguments['steps']
        if procData:
            self.bbw.bar = procData['average']
            self.bbw.cur = ( procData['bkstp'] + 1 - arguments['bkofs'] )
            self.bbw.tgt = ( procData['step'] + 1 - arguments['bkofs'] )
        else:
            self.bbw.bar = 0
            self.bbw.cur = 0
            self.bbw.tgt = 0
        self.bbw.repaint()

    # refreshes every label in additional info panel
    def updateAddData(self):
        self.AddIn.abLabel.setText('%3d' % procData['ambient'])
        self.AddIn.sbLabel.setText('%3d' % procData['screen'])
        self.AddIn.bcLabel.setText('%.1f' % procData['correction'])
        self.AddIn.bpLabel.setText('%3d%%' % procData['percent'])
        self.AddIn.ssLabel.setText('%2d' % procData['step'])
        self.AddIn.apLabel.setText('%3.2f%%' % procData['average'])
        self.AddIn.avLabel.setText('%d' % procData['valnum'])
        self.AddIn.cbLabel.setText('%2d' % procData['bkstp'])
        if type(procData['lock']) is not str:
            self.AddIn.ltLabel.setText('%.1f' % procData['lock'])
        else:
            self.AddIn.ltLabel.setText('%s' % procData['lock'])

    # bbwBarAction is connected to a signal emitted by backlight meter if the
    # user manually sets the backlight level (clicks on the bar).
    # Pauses thread execution (through pause button toggle), then attempts to
    # write obtained step value to "sysfs brightness" file
    # TODO: check if everything goes well
    def bbwBarAction(self, cur):
        if not self.PauseBtn.isChecked():
            self.PauseBtn.toggle()
        with open(arguments['path'], 'w') as fp:
            fp.write(str( int( cur-(1-arguments['bkofs'])) ) + '\n' )
        procData['bkstp'] = int( cur-(1-arguments['bkofs']))
        procData['step'] = int( cur-(1-arguments['bkofs']))
        self.changeValue()


class MainWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.okayToClose = False
        self.initUI()

    def initUI(self):
        self.setWindowTitle(infos.__CapitalName__)
        self.NormalIcon = QtGui.QIcon.fromTheme(infos.__LowerName__)
        # Desaturated (as in Disabled) main icon generation
        self.DisabledIcon = QtGui.QIcon()
        for qSize in self.NormalIcon.availableSizes():
            px = self.NormalIcon.pixmap( qSize, QtGui.QIcon.Disabled )
            self.DisabledIcon.addPixmap( px )
        self.setWindowIcon( self.NormalIcon )
        self.mainWidget = MainWid()
        self.trayIcon = QtGui.QSystemTrayIcon( self.NormalIcon, self )
        self.trayMenuBar = QtGui.QMenu()   # tray icon contextual menu
        self.CtxMenu = QtGui.QMenu()  # main window contextual menu
        self.MenuBar = self.menuBar() # main window menu bar

        # Menu QAction definitions
        aboutCalise = QtGui.QAction(
            QtGui.QIcon.fromTheme('help-about'),
            QtCore.QString.fromUtf8(_('About Calise')), self )
        aboutQt = QtGui.QAction(
            QtGui.QIcon(QtGui.QIcon.fromTheme('qtlogo').pixmap(16,16)),
            QtCore.QString.fromUtf8(_('About Qt')), self )
        exit = QtGui.QAction(
            QtGui.QIcon.fromTheme('application-exit'),
            QtCore.QString.fromUtf8(_('Exit')), self )
        self.shTray = QtGui.QAction(_( 'TrayIcon' ), self )
        self.closeToTray = QtGui.QAction(_( 'Close to tray' ), self )
        layNorm = QtGui.QAction(QtCore.QString.fromUtf8(_( 'Default' )), self)
        layExtn = QtGui.QAction(QtCore.QString.fromUtf8(_( 'Extended' )), self)
        layFull = QtGui.QAction(QtCore.QString.fromUtf8(_( 'Full' )), self)
        shMainMenu = QtGui.QAction(
            QtCore.QString.fromUtf8(_( 'Main menu' )), self )
        self.showMainWindow = QtGui.QAction(
            QtCore.QString.fromUtf8(_( 'Show window' )), self )
        # custom duplicates for tray icon contextual menu
        about = QtGui.QAction(
            QtGui.QIcon.fromTheme('help-about'),
            QtCore.QString.fromUtf8(_('About')), self )
        exit2 = QtGui.QAction(
            QtGui.QIcon.fromTheme('application-exit'),
            QtCore.QString.fromUtf8(_('Exit')), self )

        # Set QActions type
        self.shTray.setCheckable(True)
        self.closeToTray.setCheckable(True)
        layNorm.setCheckable(True)
        layExtn.setCheckable(True)
        layFull.setCheckable(True)
        shMainMenu.setCheckable(True)
        self.showMainWindow.setCheckable(True)

        # Define QAction connections
        self.shTray.toggled.connect(self.ShowHideTray)
        self.closeToTray.toggled.connect(self.setOkTo)
        exit.triggered.connect(self.OnClose)
        aboutCalise.triggered.connect(self.OnAboutCalise)
        aboutQt.triggered.connect(self.OnAboutQt)
        layNorm.triggered.connect(self.onLayNorm)
        layExtn.triggered.connect(self.onLayExtn)
        layFull.triggered.connect(self.onLayFull)
        shMainMenu.toggled.connect(self.onShowHideMainMenu)
        self.showMainWindow.toggled.connect(self.onShowMainWindow)
        about.triggered.connect(self.OnAboutCalise)
        exit2.triggered.connect(self.OnClose)

        # Set QAction Behavior
        self.shTray.toggle()
        self.closeToTray.toggle()
        layButt = QtGui.QActionGroup(self)
        layButt.setExclusive(True)
        layButt.addAction(layNorm)
        layButt.addAction(layExtn)
        layButt.addAction(layFull)
        layNorm.setChecked(True)
        shMainMenu.setChecked(True)

        # Set QActions shortcuts
        exit.setShortcut('Ctrl+Q')

        # Main menu build
        MenuFile = self.MenuBar.addMenu(QtCore.QString.fromUtf8(_( '&File' )))
        MenuFile.addAction(exit)
        MenuView = self.MenuBar.addMenu(QtCore.QString.fromUtf8(_( '&View' )))
        MenuView.addAction(self.shTray)
        MenuView.addAction(self.closeToTray)
        MenuView.addAction(shMainMenu)
        MenuView.addSeparator()
        MenuView.addAction(layNorm)
        MenuView.addAction(layExtn)
        MenuView.addAction(layFull)
        MenuHelp = self.MenuBar.addMenu(QtCore.QString.fromUtf8(_( '&Help' )))
        MenuHelp.addAction(aboutQt)
        MenuHelp.addAction(aboutCalise)

        # Trayicon menu build
        self.trayMenuBar.addAction(self.closeToTray)
        self.trayMenuBar.addSeparator()
        self.trayMenuBar.addAction(about)
        self.trayMenuBar.addAction(exit2)

        # Context menu build
        self.CtxMenu.addAction(self.closeToTray)
        self.CtxMenu.addAction(shMainMenu)
        self.CtxMenu.addSeparator()
        self.CtxMenu.addAction(layNorm)
        self.CtxMenu.addAction(layExtn)
        self.CtxMenu.addAction(layFull)
        self.CtxMenu.addSeparator()
        self.CtxMenu.addAction(exit)

        # Set tooltips
        self.trayIcon.setToolTip(QtCore.QString.fromUtf8(_( 'Camera active' )))

        self.mainWidget.AddInBtn.toggled.connect(self.OnAddIn)
        self.trayIcon.setContextMenu(self.trayMenuBar)
        self.setCentralWidget(self.mainWidget)
        QtCore.QObject.connect(
            self.mainWidget,
            QtCore.SIGNAL('pauseToggled(bool)'), self.updateTrayIcon )
        QtCore.QObject.connect(
            self.trayIcon,
            QtCore.SIGNAL('activated(QSystemTrayIcon::ActivationReason)'),
            self.__icon_activated )
        self.resize(self.minimumSize())
        self.resize(238, -1) # don't think about the 238 thing, it's arbitrary

    def OnClose(self):
        self.okayToClose = True
        self.close()

    def setOkTo(self, boolean):
        if not self.trayIcon.isVisible() and boolean is True:
            self.shTray.toggle()
        self.okayToClose = not boolean

    def onLayNorm(self):
        self.mainWidget.ExportBtn.hide()
        self.mainWidget.AddInBtn.show()
        self.mainWidget.RecordBtn.hide()

    def onLayExtn(self):
        self.mainWidget.ExportBtn.show()
        self.mainWidget.AddInBtn.hide()
        self.mainWidget.RecordBtn.show()

    def onLayFull(self):
        self.mainWidget.AddInBtn.show()
        self.mainWidget.ExportBtn.show()
        self.mainWidget.RecordBtn.show()

    def onShowHideMainMenu(self, boolean):
        self.MenuBar.setVisible(boolean)
        self.setMinimumSize(0,0)
        #self.adjustSize()
        self.mainWidget.adjustSize()
        self.resize(
            self.width(),
            self.mainWidget.height() + int(boolean)*self.MenuBar.height() )

    def onShowMainWindow(self, boolean=True):
        if boolean == True:
            self.showMainWindow.setChecked(False)
            self.trayMenuBar.removeAction(self.showMainWindow)
            self.show()
            self.move(self.lastPos)
        else:
            self.trayMenuBar.insertAction(self.closeToTray,self.showMainWindow)
            self.hide()

    # Obtains total height modification caused by AdditionalInfo widget once
    def OnAddIn(self, boolean):
        self.mainWidget.AddIn.setVisible( boolean )
        if procData != None: self.mainWidget.updateAddData()
        self.setMinimumSize(0,0)
        self.mainWidget.adjustSize()
        self.resize(
            self.width(), self.mainWidget.height() + self.MenuBar.height()
        )

    def ShowHideTray(self, boolean):
        if not self.okayToClose and not boolean:
            self.closeToTray.toggle()
        self.trayIcon.setVisible(boolean)

    def contextMenuEvent(self, event):
        action = self.CtxMenu.exec_(self.mapToGlobal(event.pos()))

    def closeEvent(self, event):
        if self.okayToClose:
            self.trayIcon.hide()
            self.mainWidget.com.td.sig = 'quit'
            while self.mainWidget.com.isRunning(): pass
            app.setQuitOnLastWindowClosed(True)
            event.accept()
        else:
            self.lastPos = self.pos()
            self.trayIcon.show()
            self.onShowMainWindow(False)
            event.ignore()

    def __icon_activated(self, reason):
        if reason == QtGui.QSystemTrayIcon.DoubleClick:
            if self.isHidden():
                self.onShowMainWindow()
            else:
                self.lastPos = self.pos()
                self.onShowMainWindow(False)

    def updateTrayIcon(self, boolean):
        if boolean:
            self.trayIcon.setIcon( self.DisabledIcon )
            self.trayIcon.setToolTip(QtCore.QString.fromUtf8(_(
                'Camera inactive' )))
                #'Camera "%s" inactive' ) % (arguments['cam']) ))
        else:
            self.trayIcon.setIcon( self.NormalIcon )
            self.trayIcon.setToolTip(QtCore.QString.fromUtf8(_(
                'Camera active' )))
                #'Camera "%s" active' ) % (arguments['cam']) ))

    def OnAboutQt(self):
        QtGui.QMessageBox.aboutQt(self,QtCore.QString.fromUtf8(_('About Qt')))

    def OnAboutCalise(self):
        QtGui.QMessageBox.about(
            self,
            QtCore.QString.fromUtf8(_('About %s' % infos.__CapitalName__)),
            QtCore.QString.fromUtf8(_(
    '<h3><b>Calise %s</b></h3><br />'
    'Calise (acronym for Camera Light Sensor) takes '
    'frames from a camera, '
    'calculates ambient brightness and sets screen\'s correct '
    'backlight level according to a user-specified scale '
    '(obtained through automatic calibration.'
    '<br /><br />'
    'Copyright &#169;  2011-2012  Nicol&ograve; Barbon'
    '<br /><br />'
    '<a href="http://sourceforge.net/projects/calise/">'
    'http://sourceforge.net/projects/calise/</a>'
    '<br /><br />'
    'Calise is free software: you can redistribute it and/or '
    'modify it under the terms of the GNU General Public '
    'License as published by the Free Software Foundation, '
    'either version 3 of the License, or any later version.<br />'
    'You should have received a copy of the GNU General Public '
    'License along with Calise.<br />If not, see '
    '<a href="http://www.gnu.org/licenses/">http://www.gnu.org/licenses/</a>.'
    '<br /><br />'
    '<b>Thanks to:</b><br />'
    ' - P&#225;draig Brady for his brief guide to gettext translation<br />'
    ' - Trent Mick for query_yes_no() function<br />'
    ' - Danny Yoo for _Getch* classes<br />'
    ' - <a href="http://zetcode.com/">ZetCode</a> for the great tutorials<br/>'
    ' - The GNOME team for the scheme of the big icon (from cheese)'
            ) % infos.__version__ ))

# subprocess launcher
class LineParser(QtCore.QThread):

    def __init__(self):
        self.td = mainLoop(nsargs)
        QtCore.QThread.__init__(self)

    def run(self):
        self.td.mainOp()
        while True:
            self.td.exeloop()
            dataDict = {}
            for idx in self.td.step1.data.keys():
                dataDict[idx] = self.td.step1.data[idx][-1]
            dataDict['average'] = self.td.ValuesAverage
            dataDict['valnum'] = len(self.td.step1.data['ambient'])
            lockTime = self.td.lock.expireTime()
            if lockTime is None or lockTime < 0:
                lockTime = _('None')
            dataDict['lock'] = lockTime
            dataDict['rec'] = self.td.args.logdata
            global procData
            procData = dataDict
            QtCore.QObject.emit( self,QtCore.SIGNAL('valueChanged()'))
            if self.td.drowsiness() is True:
                break
        self.td.mainEd()


class gui():
    def __init__(self, args):
        global arguments
        arguments = vars(args)
        global nsargs
        nsargs = args
        global app
        app = QtGui.QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        global palette
        palette = app.palette()
        main = MainWindow()
        main.show()
        sys.exit(app.exec_())