#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import getopt
import jsonrpclib
import os
import time

DEFAULT_HOST="localhost"
DEFAULT_PORT=3444

def usage(name):
    print "%s [-s server] temp" % name
    print "%s [-s server] temp set-name <sensor-id> <name>" % name
    print "%s [-s server] temp del <sensor-id>" % name
    print "%s [-s server] temp purge" % name
    print "%s [-s server] switch" % name
    print "%s [-s server] switch get <device-id> <unit-id>" % name
    print "%s [-s server] switch get <name>" % name
    print "%s [-s server] switch set <device-id> <unit-id> on|off" % name
    print "%s [-s server] switch set <name> on|off" % name
    print "%s [-s server] switch set-name <device-id> <unit-id> <name>" % name
    print "%s [-s server] switch del <name>" % name
    print "%s [-s server] button" % name
    print "%s [-s server] button set-name <name> <device-id> <unit-id>" % name
    print "%s [-s server] button bind <name> on|off <cmd>" % name
    print "%s [-s server] button unbind <name> on|off" % name
    print "%s [-s server] event" % name
    print "%s -h" % name

def make_url(host, port):
    return "http://%s:%d" % (host, port)

def temp_cmd(server):
    for sensor in server.list_temp_sensors():
        if sensor[3]:
            age = "%.0f s" % sensor[3]
        else:
            age = "unknown"
        print "Sensor %s [%d]: %3.1f °C [%s]" % (sensor[1].encode("UTF-8"), \
                                                     sensor[0], sensor[2], age)
    return 0

def temp_m_cmd(server):
    for sensor in server.list_temp_sensors():
        print "%s %3.1f" % (sensor[1].encode("UTF-8"), sensor[2])
    return 0

def temp_set_name_cmd(server, sensor_id, name):
    server.set_temp_sensor_name(sensor_id, name)
    return 0

def temp_del_cmd(server, sensor_id):
    if server.del_temp_sensor(sensor_id):
        return 0
    else:
        return 1

STALETIME=6*60*60
def temp_purge_cmd(server):
    for sensor in server.list_temp_sensors():
        if sensor[3] > STALETIME:
            if not server.del_temp_sensor(sensor[0]):
                return 1
    return 0

def state_str(state):
    if state:
        return "on"
    else:
        return "off"

def list_switches_cmd(server):
    for switch in server.list_switches():
        name = switch[2]
        if not name:
            name = "Unnamed"
        print "Switch %s [0x%x %d]: %s" % (name, switch[0], switch[1], \
                                               state_str(switch[3]))
    return 0

def get_switch_cmd(server, device_id=None, unit_id=None, name=None):
    if name:
        switch_exists, switch_state = server.get_switch_by_name(name)
    else:
        switch_exists, switch_state = \
            server.get_switch(int(device_id, 16), int(unit_id, 10))
    if switch_exists:
        print state_str(switch_state)
        return 0
    else:
        print "unknown"
        return 1

def set_switch_cmd(server, state, device_id=None, unit_id=None, 
                   name=None):
    if state == "on":
        state = 1
    elif state == "off":
        state = 0
    else:
        print 'A switch is "on" or "off"'
        sys.exit(1)
    if name:
        if server.set_switch_by_name(name, state):
            return 0
        else:
            print 'No switch "%s" exists.' % name
            return 1
    else:
        server.set_switch(int(device_id, 16), int(unit_id, 10), state)
    return 0

def set_switch_name_cmd(server, s_device_id, s_unit_id, s_name):
    server.set_switch_name(int(s_device_id, 16), int(s_unit_id, 10), s_name)
    return 0

def del_switch_cmd(server, s_name):
    if s_name == "Unnamed":
        s_name = None
    server.del_switch(s_name)
    return 0

def list_buttons_cmd(server):
    for device_id, unit_id, name, on_action, off_action in server.list_buttons():
        if name == None:
            name = "Unnamed"
        s = "Button %s [0x%x %d]" % (name, device_id, unit_id)
        if on_action != None or off_action != None:
            s += ":"
            if on_action != None:
                s += " on: \"%s\"" % on_action
            if off_action != None:
                s += " off: \"%s\"" % off_action
        print(s)
    return 0

def set_button_name_cmd(server, b_device_id, b_unit_id, b_name):
    server.set_button_name(int(b_device_id, 16), int(b_unit_id, 10), b_name)
    return 0

def bind_button_cmd(server, b_name, b_state, b_cmd):
    server.bind_button(b_name, b_state, b_cmd)
    return 0

def unbind_button_cmd(server, b_name, b_state):
    server.bind_button(b_name, b_state, None)
    return 0

def get_event_log_cmd(server):
    for event in server.get_event_log():
        (event_type, event_time, device_id, unit_id, source_name, \
             event_value) = event
        if not source_name:
            source_name = "Unnamed"
        value_s = ""
        if event_value != None:
            value_s = ": %s" % event_value
        event_time_s = time.ctime(event_time)
        unit_id_s = ""
        if unit_id != None:
            unit_id_s = " %d" % unit_id
        print "%s: %s \"%s\" [0x%x%s]%s" % (event_time_s, event_type,
                                             source_name, device_id,
                                             unit_id_s, value_s)
    return 0

env_host = os.getenv('AUTOHUB_SERVER')

if env_host:
    host = env_host
else:
    host = DEFAULT_HOST

try:
    opts, args = getopt.getopt(sys.argv[1:], "s:h")

    for opt, arg in opts:
        if opt == '-h':
            usage(sys.argv[0])
            sys.exit(0)
        elif opt == '-s':
            host = arg
        else:
            assert False
except getopt.GetoptError, err:
    print str(err)
    usage(sys.argv[0])
    sys.exit(1)

s = jsonrpclib.Server(make_url(host, DEFAULT_PORT))

if len(args) == 0:
    usage(sys.argv[0])
    sys.exit(1)

ecode = None

if args[0] == "temp":
    if len(args) == 1:
        ecode = temp_cmd(s)
    elif len(args) == 3 and args[1] == "del":
        ecode = temp_del_cmd(s, int(args[2]))
    elif len(args) == 2 and args[1] == "purge":
        ecode = temp_purge_cmd(s)
    elif len(args) == 4 and args[1] == "set-name":
        ecode = temp_set_name_cmd(s, int(args[2]), args[3])
elif args[0] == "temp-m" and len(args) == 1:
    ecode = temp_m_cmd(s)
elif args[0] == "switch":
    if len(args) == 1:
        ecode = list_switches_cmd(s)
    elif len(args) > 2:
        if args[1] == "get" and len(args) == 4:
            ecode = get_switch_cmd(s, device_id=args[2], unit_id=args[3])
        elif args[1] == "get" and len(args) == 3:
            ecode = get_switch_cmd(s, name=args[2])
        elif args[1] == "set" and len(args) == 5:
            ecode = set_switch_cmd(s, args[4], device_id=args[2],
                                   unit_id=args[3])
        elif args[1] == "set" and len(args) == 4:
            ecode = set_switch_cmd(s, args[3], name=args[2])
        elif args[1] == "set-name" and len(args) == 5:
            ecode = set_switch_name_cmd(s, args[2], args[3], args[4])
        elif args[1] == "del" and len(args) == 3:
            ecode = del_switch_cmd(s, args[2])
elif args[0] == "button":
    if len(args) == 1:
        ecode = list_buttons_cmd(s)
    elif len(args) > 2:
        if args[1] == "bind" and len(args) == 5:
            ecode = bind_button_cmd(s, args[2], args[3], args[4])
        if args[1] == "unbind" and len(args) == 4:
            ecode = unbind_button_cmd(s, args[2], args[3])
        elif args[1] == "set-name" and len(args) == 5:
            ecode = set_button_name_cmd(s, args[2], args[3], args[4])
elif args[0] == "event":
    if len(args) == 1:
        ecode = get_event_log_cmd(s)
if ecode == None:
    usage(sys.argv[0])
    sys.exit(1)
else:
    sys.exit(ecode)
