#!/usr/bin/env python

import sys, os, time, atexit
from signal import SIGTERM

#import logging


class RedirectOutput:

    def __init__(self, stdout, stdof):
        self.stdout = stdout
        self.stdof = stdof

    def write(self, s):
        with open(self.stdof, "a+") as fp:
            fp.write(s)
        #s = str(s)
        #if s[-1] == "\n":
        #    s = s[:-1]
        #if len(s) > 0:
        #    logging.info(s)

class RedirectError:

    def __init__(self, stderr, stdef):
        self.stderr = stderr
        self.stdef = stdef

    def write(self, s):
        with open(self.stdef, "a+") as fp:
            fp.write(s)
        #s = str(s)
        #if s[-1] == "\n":
        #    s = s[:-1]
        #if len(s) > 0:
        #    logging.error(s)

class RedirectInput:

    def __init__(self, stdin, stdif):
        self.stdin = stdin
        self.stdif = stdif

    def clearFile(self):
        with open(self.stdif, "w") as fp:
            fp.write("")

    def readline(self):
        if not os.path.isfile(self.stdif):
            return ""
        with open(self.stdif, "r") as fp:
            line = fp.readline()
        self.clearFile()
        return line


class Daemon:
	"""
	A generic daemon class.

	Usage: subclass the Daemon class and override the run() method
	"""
	def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
		self.stdin = stdin
		self.stdout = stdout
		self.stderr = stderr
		self.pidfile = pidfile
		#logging.basicConfig(
               #     filename=self.stdout, level=logging.INFO,
               #     format="%(levelname)s: %(message)s" )
               #     #format="%(asctime)s: %(levelname)s: %(message)s" )

	def daemonize(self):
		"""
		do the UNIX double-fork magic, see Stevens' "Advanced
		Programming in the UNIX Environment" for details (ISBN 0201563177)
		http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
		"""
		try:
			pid = os.fork()
			if pid > 0:
				# exit first parent
				sys.exit(0)
		except OSError, e:
			sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)

		# decouple from parent environment
		os.chdir("/")
		os.setsid()
		os.umask(0)

		# do second fork
		try:
			pid = os.fork()
			if pid > 0:
				# exit from second parent
				sys.exit(0)
		except OSError, e:
			sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)

                # redirect standard file descriptors
                #si = open(self.stdin, 'r')
                #so = open(self.stdout, 'a+')
                #se = open(self.stderr, 'a+', 0)
                #os.dup2(si.fileno(), sys.stdin.fileno())
                #os.dup2(so.fileno(), sys.stdout.fileno())
                #os.dup2(se.fileno(), sys.stderr.fileno())
                sys.stdin = RedirectInput(sys.stdin,self.stdin)
                sys.stdout = RedirectOutput(sys.stdout,self.stdout)
                sys.stderr = RedirectError(sys.stderr,self.stderr)
                sys.stdout.write("")

		# write pidfile
		atexit.register(self.delpid)
		pid = str(os.getpid())

		with open(self.pidfile,'w+') as pf:
                    pf.write("%s\n" % pid)

	def delpid(self):
		os.remove(self.pidfile)

	def start(self):
		"""
		Start the daemon
		"""
		# Check for a pidfile to see if the daemon already runs
		try:
			with open(self.pidfile,'r') as pf:
                            pid = int(pf.read().strip())
		except IOError:
			pid = None

		if pid:
			message = "pidfile %s already exist. Daemon already running?\n"
			sys.stderr.write(message % self.pidfile)
			sys.exit(1)

		# Start the daemon
		self.daemonize()
		self.run()

	def stop(self):
		"""
		Stop the daemon
		"""
		# Get the pid from the pidfile
		try:
			with open(self.pidfile,'r') as pf:
                            pid = int(pf.read().strip())
		except IOError:
			pid = None

		if not pid:
			message = "pidfile %s does not exist. Daemon not running?\n"
			sys.stderr.write(message % self.pidfile)
			return # not an error in a restart

		# Try killing the daemon process	
		try:
			while 1:
				os.kill(pid, SIGTERM)
				time.sleep(0.1)
		except OSError, err:
			err = str(err)
			if err.find("No such process") > 0:
				if os.path.exists(self.pidfile):
					os.remove(self.pidfile)
			else:
				print str(err)
				sys.exit(1)

	def restart(self):
		"""
		Restart the daemon
		"""
		self.stop()
		self.start()

	def run(self):
		"""
		You should override this method when you subclass Daemon. It will be called after the process has been
		daemonized by start() or restart().
		"""
