#!/usr/bin/python

import sys
import serial
import time
import threading
import syslog
import struct

TYPE_INTERFACE_CONTROL = 0x0
SUBTYPE_INTERFACE_COMMAND = 0x0
COMMAND_RESET = 0x0
COMMAND_STATUS = 0x2
COMMAND_ENABLE_UNDECODED = 0x5
COMMAND_ENABLE_ALL = 0x4

TYPE_INTERFACE_MESSAGE = 0x1
SUBTYPE_INTERFACE_RESPONSE = 0x0

TYPE_TEMP_MESSAGE = 0x50
SUBTYPE_TEMP_LACROSSE = 0x5
SUBTYPE_TEMP_VIKING_02811 = 0x7

TYPE_UNDECODED_MESSAGE = 0x3
SUBTYPE_UNDECODED_LACROSSE = 0x4

TYPE_LIGHTING2_MESSAGE = 0x11
SUBTYPE_LIGHTING2_AC = 0x0

SUBTYPE_LIGHTING2_ANSLUT = 0x2

TYPE_REMOTE_MESSAGE = 0x30

class Decoder:
    def __init__(self, status_cb, temp_cb, button_cb):
        self.packet_data = ""
        self.status_cb = status_cb
        self.temp_cb = temp_cb
        self.button_cb = button_cb
    def packet_done(self):
        data_len = len(self.packet_data)
        return data_len > 0 and data_len == (ord(self.packet_data[0])+1)
    def put_char(self, c):
        self.packet_data += c
        if self.packet_done():
            self.parse_packet()
            self.reset()
            return True
        else:
            return False
    def get_byte(self, index):
        return ord(self.packet_data[index])
    def get_uint(self, index):
        return struct.unpack_from("!I", self.packet_data, index)[0]
    def parse_packet(self):
        if len(self.packet_data) <= 1:
            syslog.syslog(syslog.LOG_WARNING, "Got too short packet (%d bytes)." % len(self.packet_data))
            return
        ptype = self.get_byte(1)
        if ptype == TYPE_INTERFACE_MESSAGE:
            self.parse_interface_control()
        elif ptype == TYPE_UNDECODED_MESSAGE:
            self.parse_undecoded()
        elif ptype == TYPE_TEMP_MESSAGE:
            self.parse_temp()
        elif ptype == TYPE_LIGHTING2_MESSAGE:
            self.parse_lighting2()
        else:
            syslog.syslog(syslog.LOG_DEBUG, "Unknown packet type 0x%x" % ptype)
    def parse_temp(self):
        subtype = self.get_byte(2)
        if subtype == SUBTYPE_TEMP_LACROSSE or SUBTYPE_TEMP_VIKING_02811:
            seq_no = self.get_byte(3)
            addr = self.get_byte(4)<<8 + self.get_byte(5)
            if (self.get_byte(6) & 0x80) == 0:
                temp = (self.get_byte(6)*256+self.get_byte(7)) / 10.0
            else:
                temp = - ((self.get_byte(6) & 0x7F)*256 + self.get_byte(7)) / 10.0
            signal_level = (self.get_byte(8) & 0xf0) >> 4
            self.temp_cb(addr, seq_no, temp, signal_level)
            if self.get_byte(8) & 0xf == 0:
                syslog.syslog(syslog.LOG_WARNING,
                              "Battery for sensor %d is low." % addr)
        else:
            syslog.syslog(syslog.LOG_DEBUG,
                          "Unknown temperature message subtype 0x%x" % subtype)
    def parse_lighting2(self):
        subtype = self.get_byte(2)
        if subtype == SUBTYPE_LIGHTING2_AC:
            seq_no = self.get_byte(3)
            addr = self.get_uint(4)
            unit = self.get_byte(8)
            state = self.get_byte(9)
            signal_level = (self.get_byte(11) & 0xf0) >> 4
            syslog.syslog(syslog.LOG_DEBUG, "Lighting 2 - AC type message received. Seqno %d, device address 0x%x, unit %d, state %d, signal_level %d." % (seq_no, addr, unit, state, signal_level))
            self.button_cb(addr, unit, state)
        else:
            syslog.syslog(syslog.LOG_WARNING,
                          "Unknown Lighting 2 subtype 0x%x" % state)
    def parse_undecoded(self):
        subtype = self.get_byte(2)
        if subtype == SUBTYPE_UNDECODED_LACROSSE:
            msg = ""
            for b in self.packet_data[2:]:
                msg += ("%d " % ord(b))
            msg += "\n"
            for b in self.packet_data[2:]:
                msg += ("[%d %d] " % (ord(b)&0xf, (ord(b)>>4)&0xf))
            msg += "\n"
            for b in self.packet_data[2:]:
                for i in range(7, -1, -1):
                    if (ord(b) >> i) & 1 == 1:
                        msg += "1"
                    else:
                        msg += "0"
                msg += " "
            msg += "\n"
        else:
            syslog.syslog(syslog.LOG_DEBUG,
                          "Unknown undecoded message subtype 0x%x" % subtype)
        
    def parse_interface_control(self):
        subtype = self.get_byte(2)
        if subtype == SUBTYPE_INTERFACE_RESPONSE:
            self.parse_interface_response()
        else:
            syslog.syslog(syslog.LOG_DEBUG,
                          "Unknown interface control packet 0x%x" % subtype)
    def parse_interface_response(self):
        cmd = self.get_byte(4)
        if cmd == COMMAND_STATUS:
            firmware_rev = self.get_byte(6)
            self.status_cb(firmware_rev)
        else:
            syslog.syslog(syslog.LOG_DEBUG,
                          "Unknown interface response for command 0x%x" % cmd)
    def reset(self):
        self.packet_data = ""

def pad(ary, plen):
    while len(ary) < plen:
        ary += chr(0)
    return ary

RESEND_TIMES = 3
RESEND_DELAY = 0.15

class RFXtrx433 (threading.Thread):
    def __init__(self, dev_filename, temp_cb, button_cb):
        threading.Thread.__init__(self)
        self.daemon = True
        self.dev_filename = dev_filename
        self._seq = 1
        self._decoder = Decoder(self._handle_status_response,
                                temp_cb, button_cb)
        self.firmware_rev = None
        self.shouldStop = False
    def init(self):
        self._open()
        self._reset()
        self._enable_all()
        self._process_response()
#        self._enable_undecoded()
#        self._process_response()
        self._status()
        self._process_response()
    def close(self):
        self._dev.close()
    def set_switch(self, device_id, unit_id, seq_no, state):
        for i in range(0, RESEND_TIMES):
            self._set_switch(device_id, unit_id, seq_no, state)
            time.sleep(RESEND_DELAY)
    def _set_switch(self, device_id, unit_id, seq_no, state):
        # we assume all switches are "lighting 2" type
        if state:
            state_code = 1
        else:
            state_code = 0
        payload = struct.pack("!BBBIBBBBB",
                              TYPE_LIGHTING2_MESSAGE,
                              SUBTYPE_LIGHTING2_AC,
                              seq_no,
                              device_id,
                              unit_id,
                              state_code,
                              0, # group
                              0, # dim value
                              0, # dunno
                              )
        self._write_packet(payload)
    def _open(self):
        self._dev = serial.Serial(port=self.dev_filename,
                                  parity=serial.PARITY_NONE,
                                  stopbits=serial.STOPBITS_ONE,
                                  bytesize=serial.EIGHTBITS,
                                  baudrate=38400,
                                  timeout=0.3)
    def _nextSeq(self):
        this = self._seq
        self._seq += 1
        if self._seq >= 256:
            self._seq = 1
        return this
    def _write_packet(self, payload):
        #packet = chr(len(payload))
        packet = struct.pack("!H", len(payload))
        packet += payload
        self._dev.write(packet)
        self._dev.flush()
    def _reset(self):
        syslog.syslog(syslog.LOG_DEBUG,
                      "Resetting device.")
        self._issue_interface_command(COMMAND_RESET)
        syslog.syslog(syslog.LOG_DEBUG,
                      "Waiting for device to boot up.")
        time.sleep(2)
    def _enable_undecoded(self):
        syslog.syslog(syslog.LOG_DEBUG, "Enabling undecoded")
        self._issue_interface_command(COMMAND_ENABLE_UNDECODED)
        self._process_response()
    def _enable_all(self):
        syslog.syslog(syslog.LOG_DEBUG, "Enabling all")
        self._issue_interface_command(COMMAND_ENABLE_ALL)
        self._process_response()
    def _status(self):
        syslog.syslog(syslog.LOG_DEBUG, "Issued status.")
        self._issue_interface_command(COMMAND_STATUS)
        self._process_response()
    def _handle_status_response(self, firmware_rev):
        syslog.syslog(syslog.LOG_DEBUG, "Firmware revision: %d" % firmware_rev)
        self.firmware_rev = firmware_rev
    def _issue_interface_command(self, cmd):
        self._write_packet(chr(TYPE_INTERFACE_CONTROL) + \
                              chr(SUBTYPE_INTERFACE_COMMAND) + \
                              chr(self._nextSeq()) + \
                              chr(cmd))
    def _process_response(self):
        completed = False
        while not completed:
            c = self._dev.read(1)
            if not c:
                return # timeout
            completed = self._decoder.put_char(c)
    def halt(self):
        self.shouldStop = True
        self._dev.close()
        self.join()
    def run(self):
        self.init()
        while not self.shouldStop:
            self._process_response()


