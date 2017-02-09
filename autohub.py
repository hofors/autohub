#!/usr/bin/python
# -*- coding: utf-8 -*-

#
# Autohub - a small home automation hub, capable of managing switches and
#           temp sensors using the RFXtrx433 transeiver.
#
# Author: Mattias Rönnblom <hofors@lysator.liu.se>
#
# This package is GNU GPL v2.
#


import time
import rfxtrx433
import sys
import signal
import threading
import os
import jsonrpcif
import syslog
import getopt
import shelve

class TempSensor:
    def __init__(self, sensor_id):
        self.sensor_id = sensor_id
        self.name = None
        self.last_update = None
        self.hum = None
    def update(self, temp, signal_level, hum=None):
        self.last_update = time.time()
        self.temp = temp
        self.hum = hum
        self.signal_level = signal_level

EVENT_TYPE_BUTTON_PRESSED = "button-pressed"
EVENT_TYPE_SENSOR_READING = "sensor-reading"
EVENT_TYPE_SWITCH_SET = "switch-set"

class Event:
    def __init__(self, event_type, event_time, device_id, unit_id, source_name,
                 event_value):
        self.event_type = event_type
        self.event_time = event_time
        self.device_id = device_id
        self.unit_id = unit_id
        self.source_name = source_name
        self.event_value = event_value

class Switch:
    def __init__(self, device_id, unit_id, name=None, state=None,
                 last_update=None):
        self.device_id = device_id
        self.unit_id = unit_id
        self.name = name
        self.state = state
        self.last_update = last_update
        self.seq_no = 0
    def update(self, state):
        self.last_update = time.time()
        self.state = state
    def next_seq_no(self):
        seq_no = self.seq_no
        self.seq_no += 1
        if self.seq_no > 255:
            self.seq_no = 0
        return seq_no
    def state_str(self):
        if self.state:
            return "on"
        else:
            return "off"

def synchronized():
    '''Synchronization decorator.'''
    def wrap(f):
        def new_function(self, *args, **kw):
            self._lock.acquire()
            try:
                return f(self, *args, **kw)
            finally:
                self._lock.release()
        return new_function
    return wrap

MAX_EVENT_LOG_SIZE = 10000

class AutoHub:
    def __init__(self, dev_filename, state_filename):
        self._rfxtrx433 = rfxtrx433.RFXtrx433(dev_filename, self._handle_temp)
        self.temp_sensors = {}
        self.switches = []
        self.event_log = []
        self._lock = threading.RLock()
        self.state_filename = state_filename
        self._load()
    def start(self):
        self._rfxtrx433.start()
    def halt(self):
        self._rfxtrx433.halt()
    def lock(self):
        self._lock.acquire()
    def unlock(self):
        self._save()
        self._lock.release()
    @synchronized()
    def set_switch_by_name(self, name, state):
        assert self.has_switch_by_name(name)
        switch = self.get_switch_by_name(name)
        self._set_switch(switch, state)
    @synchronized()
    def has_switch_by_name(self, name):
        return self._switch_index_by_name(name) != -1
    @synchronized()
    def get_switch_by_name(self, name):
        idx = self._switch_index_by_name(name)
        assert idx != -1
        return self.switches[idx]
    @synchronized()
    def set_switch_name(self, device_id, unit_id, name):
        assert self.has_switch(device_id, unit_id)
        switch = self.get_switch(device_id, unit_id)
        switch.name = name
    @synchronized()
    def set_switch(self, device_id, unit_id, state):
        if not self.has_switch(device_id, unit_id):
            self.switches.append(Switch(device_id, unit_id))
        switch = self.get_switch(device_id, unit_id)
        self._set_switch(switch, state)
    def _set_switch(self, switch, state):
        old_state_str = switch.state_str()
        switch.update(state)
        self._rfxtrx433.set_switch(switch.device_id, switch.unit_id,
                                   switch.next_seq_no(), state)
        syslog.syslog(syslog.LOG_INFO, "Setting switch \"%s\" (0x%x %x) "
                      "from %s to %s." % (switch.name.encode("UTF-8"),
                                          switch.device_id, switch.unit_id,
                                          old_state_str, switch.state_str()))
        self.add_event(EVENT_TYPE_SWITCH_SET, switch.device_id,
                       switch.unit_id, switch.name, switch.state_str())
    def _switch_index(self, device_id, unit_id):
        for i in range(0, len(self.switches)):
            s = self.switches[i]
            if s.device_id == device_id and s.unit_id == unit_id:
                return i
        return -1
    def _switch_index_by_name(self, name):
        for i in range(0, len(self.switches)):
            s = self.switches[i]
            if s.name == name:
                return i
        return -1
    @synchronized()
    def has_switch(self, device_id, unit_id):
        return self._switch_index(device_id, unit_id) != -1
    @synchronized()
    def get_switch(self, device_id, unit_id):
        idx = self._switch_index(device_id, unit_id)
        assert idx != -1
        return self.switches[idx]
    @synchronized()
    def clear_event_log(self):
        self.event_log = []
    @synchronized()
    def add_event(self, event_type, device_id, unit_id, source_name,
                  event_value):
        self.event_log.append(Event(event_type, time.time(), device_id, unit_id,
                                    source_name, event_value))
        while len(self.event_log) > MAX_EVENT_LOG_SIZE:
            del self.event_log[0]
    @synchronized()
    def _handle_temp(self, sensor_id, seq_no, temp, signal_level, hum):
        syslog.syslog(syslog.LOG_DEBUG, "Got reading from sensor 0x%x; "
                      "seq no %d; signal level %d; temperature %3.2f; "
                      "humidity %s%%;" % \
                          (sensor_id, seq_no, signal_level, temp, hum))
        if not self.temp_sensors.has_key(sensor_id):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Sensor %d has not been seen before." % sensor_id)
            self.temp_sensors[sensor_id] = TempSensor(sensor_id)
        sensor = self.temp_sensors[sensor_id]
        sensor.update(temp,  signal_level, hum)
        self.add_event(EVENT_TYPE_SENSOR_READING, sensor.sensor_id, 0,
                       sensor.name, str(sensor.temp))
    def _load(self):
        s = shelve.open(self.state_filename)
        if s.has_key("switches"):
            self.switches = s["switches"]
        if s.has_key("temp_sensors"):
            self.temp_sensors = s["temp_sensors"]
        if s.has_key("event_log"):
            self.event_log = s["event_log"]
        s.close()
    def _save(self):
        s = shelve.open(self.state_filename)
        s["switches"] = self.switches
        s["temp_sensors"] = self.temp_sensors
        s["event_log"] = self.event_log
        s.close()


def quit(signum, frame):
    syslog.syslog(syslog.LOG_INFO, "Quitting.")
    sys.exit(1)

def usage(name):
    print "Usage: %s [-F <rfxcom-dev>] [-f <state-file>]" % name

DEFAULT_DEV_FILENAME = "/dev/ttyUSB0"
DEFAULT_STATE_FILENAME = "autohub.dat"

debug = False
dev_filename = DEFAULT_DEV_FILENAME
state_filename = DEFAULT_STATE_FILENAME

try:
    opts, args = getopt.getopt(sys.argv[1:], "hdf:F:", ["help"])
    for o, a in opts:
        if o == "-d":
            debug = True
        elif o == "-f":
            state_filename = a
        elif o == "-F":
            dev_filename = a
        elif o in ("-h", "--help"):
            usage(sys.argv[0])
            sys.exit(0)
        else:
            assert False, "unhandled option"
except getopt.GetoptError, err:
    print str(err)
    usage(sys.argv[0])
    sys.exit(1)

if len(args) != 0:
    usage(sys.argv[0])
    sys.exit(1)


syslog.openlog("autohub", syslog.LOG_PERROR, syslog.LOG_DAEMON)

if not debug:
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_INFO))

signal.signal(signal.SIGHUP, quit)
signal.signal(signal.SIGQUIT, quit)
signal.signal(signal.SIGTERM, quit)
signal.signal(signal.SIGINT, quit)

autohub = AutoHub(dev_filename, state_filename)
jif = jsonrpcif.JSONRPCIf(autohub)
shouldStop = False
jif.start()
autohub.start()
while not shouldStop:
    time.sleep(1)
autohub.halt()
hif.halt()
