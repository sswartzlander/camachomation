import sys

class Command:
    def __init__(self,toAddress,cmd1,cmd2,flags,deviceName):
        self.toAddress = toAddress
        self.cmd1 = cmd1
        self.cmd2 = cmd2
        self.flags = flags
        self.deviceName = deviceName
