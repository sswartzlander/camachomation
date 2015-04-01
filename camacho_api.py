import sys
from camacho_command import Command
from bottle import Bottle, template


class CamachoAPI:   
    def __init__(self,plm,host,port):
        self._plm = plm
        self._host = host
        self._port = port
        self._app = Bottle()
        self._route()

    def _route(self):
        self._app.route('/on/<deviceName>/<level:int>', callback=self._on)
        self._app.route('/on/<deviceName>', callback=self._on)
        self._app.route('/off/<deviceName>', callback=self._off)
        
    def _on(self,deviceName,level=100):
        device = self._plm.getDeviceForName(deviceName)
        
        onLevel = hex(int((level/100)*255))[2:].upper()
        cmd = Command(device.address.upper(),'11',onLevel,'0F',deviceName)
        self._plm.enqueueOutboundCommand(cmd)

    def _off(self,deviceName):
        device = self._plm.getDeviceForName(deviceName)
        cmd = Command(device.address.upper(),'13','00','0F',deviceName)
        
        self._plm.enqueueOutboundCommand(cmd)

    def start(self):
        self._app.run(host=self._host, port=self._port, debug=True)


