#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import getopt
import jsonrpclib
import os
import datetime
import syslog

DEFAULT_HOST="localhost"
DEFAULT_PORT=3444

OUTSIDE_SENSOR="Ute"
HEATER_SWITCH="Motorvärmare"

OVERSLEEPING=30

def make_url(host, port):
    return "http://%s:%d" % (host, port)

def get_temp(server, sensor_name):
    for sensor in server.list_temp_sensors():
        if sensor[1] == sensor_name:
	    return sensor[2]
    return None

def set_switch(server, switch_name, state):
    server.set_switch_by_name(switch_name, state)

def heating_time(temp):
    if temp < -15:
        return 3*60
    elif temp < 15:
        return 30+(-temp+15.0)/30*(2*60+30)
    else:
        return 30

def usage(n):
    print "%s <target-time>" % n

def to_datetime(hour, minute):
    now = datetime.datetime.now()
    return datetime.datetime(year=now.year, month=now.month, day=now.day,
                             hour=hour, minute=minute)

def start_time(target, heat_t):
    start = target - datetime.timedelta(minutes=heat_t)
    now = datetime.datetime.now()
    if start < now:
        syslog.syslog("Heating should already have started.")
        start = now+datetime.timedelta(minutes=1)
    return start

def target_time(target_h, target_m):
    target = to_datetime(target_h, target_m)
    if datetime.datetime.now() > target:
        target += datetime.timedelta(hours=24)
    return target

def schedule_switch(state, t):
    if state:
        state_s = "on"
    else:
        state_s = "off"
    s = "echo ahc switch set %s %s | at %02d:%02d" % (HEATER_SWITCH, state_s, t.hour, t.minute)
    os.system(s)

env_host = os.getenv('AUTOHUB_SERVER')

if env_host:
    host = env_host
else:
    host = DEFAULT_HOST

if len(sys.argv) != 2:
    usage(sys.argv[0])
    sys.exit(1)

target_h_s, target_m_s = sys.argv[1].split(":")

target_h = int(target_h_s)
target_m = int(target_m_s)

target = target_time(target_h, target_m)

s = jsonrpclib.Server(make_url(host, DEFAULT_PORT))

temp = get_temp(s, OUTSIDE_SENSOR)
heat_t = heating_time(temp)
start = start_time(target, heat_t)
stop = target + datetime.timedelta(minutes=OVERSLEEPING)

syslog.syslog("Target time is %02d:%02d. Outside temp is %3.1f. Heating time is %d minutes. Start time is %02d:%02d. Stop time is %02d:%02d." % (target.hour, target.minute, temp, heat_t, start.hour, start.minute, stop.hour, stop.minute))

schedule_switch(True, start)
schedule_switch(False, stop)
