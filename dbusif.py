import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import threading
import gobject
 
class AutoHubService(dbus.service.Object):
    def __init__(self, autohub):
        bus_name = dbus.service.BusName('se.liu.lysator.autohubservice', bus=dbus.SessionBus())
        dbus.service.Object.__init__(self, bus_name, '/se/liu/lysator/autohubservice')
        self.autohub = autohub
    @dbus.service.method(dbus_interface='se.liu.lysator.autohubservice',
                         out_signature='a(ud)')
    def temp(self):
        result = []
        self.autohub.lock()
        for s in self.autohub.temp_sensors.values():
            result.append((s.sensor_id, s.temp))
        self.autohub.unlock()
        return result
    

class DBusIf (threading.Thread):
    def __init__(self, autohub):
        threading.Thread.__init__(self)
        self.daemon = True
        self.autohub = autohub
    def run(self):
        DBusGMainLoop(set_as_default=True)
        autohubservice = AutoHubService(self.autohub)
        loop = gobject.MainLoop()
        loop.run()

gobject.threads_init()
