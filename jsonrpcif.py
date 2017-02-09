from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer
import threading
import traceback
import time

DEFAULT_PORT=3444

class JSONRPCIf (threading.Thread):
    def __init__(self, autohub):
        threading.Thread.__init__(self)
        self.daemon = True
        self.autohub = autohub
        self.server = SimpleJSONRPCServer(('', DEFAULT_PORT),
                                          logRequests=False)
        for f in [ self.list_temp_sensors, self.list_switches, \
                       self.get_switch, self.set_switch, \
                       self.set_switch_name, self.set_switch_by_name, \
                       self.get_switch_by_name, \
                       self.set_temp_sensor_name, \
                       self.del_temp_sensor, \
                       self.get_event_log]:
            self.server.register_function(f)
    def list_temp_sensors(self):
        result = []
        self.autohub.lock()
        for s in self.autohub.temp_sensors.values():
            if s.name == None:
                name = "%d" % s.sensor_id
            else:
                name = s.name
            if s.last_update:
                age = time.time()-s.last_update
            else:
                age = None
            if s.hum == None:
                result.append((s.sensor_id, name, s.temp, age, None))
            else:
                result.append((s.sensor_id, name, s.temp, age, s.hum))

        self.autohub.unlock()
        return result
    def del_temp_sensor(self, sensor_id):
        self.autohub.lock()
        sensors = self.autohub.temp_sensors
        if sensors.has_key(sensor_id):
            del sensors[sensor_id]
            retval = True
        else:
            retval = False
        self.autohub.unlock()
        return retval
    def set_temp_sensor_name(self, sensor_id, name):
        self.autohub.lock()
        if self.autohub.temp_sensors.has_key(sensor_id):
            self.autohub.temp_sensors[sensor_id].name = name
            result = True
        else:
            result = False
        self.autohub.unlock()
        return result
    def list_switches(self):
        result = []
        self.autohub.lock()
        for s in self.autohub.switches:
            result.append((s.device_id, s.unit_id, s.name, s.state))
        self.autohub.unlock()
        return result
    def get_switch(self, device_id, unit_id):
        self.autohub.lock()
        if not self.autohub.has_switch(device_id, unit_id):
            result = [ False, None ]
        else:
            s = self.autohub.get_switch(device_id, unit_id)
            result = [ True, s.state ]
        self.autohub.unlock()
        return result
    def set_switch(self, device_id, unit_id, state):
        self.autohub.lock()
        try:
            self.autohub.set_switch(device_id, unit_id, state)
        except Exception as e:
            traceback.print_exc()
        self.autohub.unlock()
    def set_switch_name(self, device_id, unit_id, name):
        self.autohub.lock()
        try:
            self.autohub.set_switch_name(device_id, unit_id, name)
        except Exception as e:
            traceback.print_exc()
        self.autohub.unlock()
    def set_switch_by_name(self, name, state):
        result = None
        self.autohub.lock()
        try:
            if self.autohub.has_switch_by_name(name):
                self.autohub.set_switch_by_name(name, state)
                result = True
            else:
                result = False
        except Exception as e:
            traceback.print_exc()
        self.autohub.unlock()
        return result
    def get_switch_by_name(self, name):
        self.autohub.lock()
        if not self.autohub.has_switch_by_name(name):
            result = [ False, None ]
        else:
            s = self.autohub.get_switch_by_name(name)
            result = [ True, s.state ]
        self.autohub.unlock()
        return result
    def get_event_log(self):
        result = []
        self.autohub.lock()
        for e in self.autohub.event_log:
            result.append((e.event_type, e.event_time, e.device_id,
                           e.unit_id, e.source_name, e.event_value))
        self.autohub.unlock()
        return result
    def run(self):
        self.server.serve_forever()
