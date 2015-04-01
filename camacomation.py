import sys
import base64
import serial
import time
import threading
import serial
import binascii
import device
import camacho_command
import camacho_api
from collections import deque
from bottle import route, run

class PLM:
    def __init__(self, comPort):
        self._plm = serial.Serial(comPort, 19200, timeout=2)
        self._outboundQueue = deque()
        self.running = True
        self._buffer = ''
        self._lastCommandSent = ''
        # define PLM command information
        self._plmRxCommands = {'50': { # STD Received
                                'size': 9},
                             '51': { # EXT Received
                                 'size': 23},
                             '52': { # X10 Received
                                 'size': 2},
                             '53': { # All-Linking Complete
                                 'size': 8},
                             '54': { # Button Report Event
                                 'size': 1},
                             '55': { # User Reset Detected
                                 'size':0},
                             '56': { # All-Link Cleanup Failure
                                 'size': 5},
                             '57': { # All-Link Record Reponse
                                 'size': 8},
                             '58': { # All-Link Cleanup Status Report
                                 'size': 1}}
        self._plmTxCommands = {'60': { # Get IM Info
                                   'size': 7},
                               '61': { # Send All-Link Command
                                   'size': 4},
                               '62': { # Send STD/EXT Message
                                   'size': 7},
                               '63': { # Send X10
                                   'size': 3},
                               '64': { # Start All-Linking
                                   'size': 3},
                               '65': { # Cancel All-Linking
                                   'size': 1},
                               '66': { # Set Host Device Cat
                                   'size': 4},
                               '67': { # Reset IM
                                   'size': 1},
                               '68': { # Set Insteon ACK Message Byte
                                   'size': 2},
                               '69': { # Get First All-Link Record
                                   'size': 1},
                               '6A': { # Get Next All-Link Record
                                   'size': 1},
                               '6B': { # Set IM Configuration
                                   'size': 2},
                               '6C': { # Get All-Link Record for Sender
                                   'size': 1},
                               '6D': { # LED On
                                   'size': 1},
                               '6E': { # LED Off
                                   'size': 1},
                               '6F': { # Manage All-Link Record
                                   'size': 10},
                               '70': { # Set Insteon NAK Message Byte
                                   'size': 2},
                               '71': { # Set Insteon ACK Message Two Bytes
                                   'size': 3},
                               '72': { # RF Sleep
                                   'size': 1},
                               '73': { # Get IM Configuration
                                   'size': 4}}
        
        self._devices = {}
        config = open('camacho.conf','r')

        for line in config:
            contents = line.strip().split('=')
            devName = contents[0]
            devAddress = contents[1]
            
            dev = device.Device(devName,devAddress)
            
            self._devices[devName.lower()] = dev

        print(self._devices)

    def getDeviceForName(self, deviceName):
        return self._devices[deviceName.lower()]
                             
                             
    def decodeMessageFlag(self, msgFlag):
        if msgFlag & 224 == 128:
            return 'SA Broadcast'
        elif msgFlag & 224 == 192:
            return 'SB Broadcast'
        elif msgFlag & 224 == 64:
            return 'SC Cleanup'
        elif msgFlag & 224 == 96:
            return 'SC Cleanup ACK'
        elif msgFlag & 224 == 0:
            return 'SD Direct'
        elif msgFlag & 224 == 32:
            return 'SD ACK'
        elif msgFlag & 224 == 160:
            return 'SD NAK'
        else:
            return 'Unknown'
                                     

    # processes sending messages 
    def processSendBuffer(self):
        while self.running:
            time.sleep(0.1)
            if len(self._outboundQueue) > 0:
                
                command = self._outboundQueue.pop();

                str = '0262' + command.toAddress + command.flags + command.cmd1 + command.cmd2

                print('command being sent... %s' % str)
                packet = base64.b16decode(str)

                self._lastCommandSent = str
                self._plm.write(packet)
                

        print("Send thread exiting.\n")
        return

    def enqueueOutboundCommand(self, outboundCommand):
        print('Enqueued command to: %s.  Cmd1: %s, Cmd2: %s' % (outboundCommand.toAddress, outboundCommand.cmd1, outboundCommand.cmd2))
        self._outboundQueue.append(outboundCommand)

    def processReceiveBuffer(self):
        while self.running:
            time.sleep(0.1)
            charsToRead = self._plm.inWaiting()
            if charsToRead > 0:
                self._buffer = self._buffer + binascii.hexlify(self._plm.read(charsToRead)).decode("utf-8").upper()     
                print('bytes read: %d, buffer size: %d\n' % (charsToRead, len(self._buffer)))
            # process conents of buffer if necessary
            if len(self._buffer) > 4:
                lengthOfLastMessage = self.processMessage(self._buffer)
                self._buffer = self._buffer[lengthOfLastMessage:]

        print("Receive thread exiting.\n")
        return

    def processMessage(self, buffer):
        if buffer[0:2] != '02' or len(buffer) < 4: # TODO: clear buffer on bad data?
            print('buffer starts with bad data: ' + buffer)
            return 0 
        else:
            
            #if the _lastCommandSent is populated, check for an ack
            if self._lastCommandSent != '':
                if len(buffer) >= 2 + len(self._lastCommandSent):
                    message = buffer[0:len(self._lastCommandSent)]
                    if (message == self._lastCommandSent):
                        ack = buffer[len(self._lastCommandSent):2+len(self._lastCommandSent)]
                        print('Last message ACK? %s'% ack)
                        messageLength = len(self._lastCommandSent) + 2
                        self._lastCommandSent = ''
                        return messageLength

            
            messageType = buffer[2:4]
            messageLength = 4 + self._plmRxCommands[messageType]['size']*2
            
            # if the buffer doesn't have the full message in it, wait
            if len(buffer) < messageLength:
                return 0
            
            message = buffer[0:messageLength]
            print('rx: %s\n' % message)
            
            if messageType == '50': # STD MSG RX
                # 02 50
                # 3 from address bytes
                # 3 to bytes address or broadcast message 11xx xxxx flags it is the group
                # 1 byte flag
                # 2 bytes command

                msgFrom = message[4:10]
                msgTo = message[10:16]
                msgFlag = bytearray.fromhex(message[16:18])[0]
                msgCmd = message[18:22]

                if msgFrom.lower() in self._devices:            
                    sourceDevice = self._devices[msgFrom.lower()]
                else:
                    sourceDevice = device.Device('unknown','??????')
                
                flagType = self.decodeMessageFlag(msgFlag)
                print('From: %s, RX Flag: %s\n' % (sourceDevice.name, flagType))                         

            elif messageType == '51': # EXT MSG RX
                # 02 51
                # 3 from address bytes
                # 3 to bytes address or broadcast message 11xx xxxx flags it is the group
                # 1 byte flag
                # 2 bytes command
                # 14 bytes user data

                msgFrom = message[4:10]
                msgTo = message[10:16]
                msgFlag = message[16:18]
                msgCmd = message[18:22]
                msgUserData = message[22:50]

            elif messageType == '52': # X10 MSG RX
                # 02 52
                # 1 byte Raw X10
                # 1 byte X10 Flag

                msgRwX10 = message[4:6]
                msgX10Flag = message[6:8]
                
            elif messageType == '53': # All-Linking Complete
                # 02 53
                # 1 byte link code
                # 1 byte All-Link group
                # 3 bytes device ID
                # 1 byte DevCAt
                # 1 byte SubCat
                # 1 byte firmware

                msgLinkCode = message[4:6] # 00 means IM is responder, 01 means IM is controller, FF means link to device was deleted
                msgGroupID = message[6:8]
                msgFrom = message[8:14]
                msgDevCat = message[14:16]
                msgSubCat = message[16:18]
                msgFirmware = message[18:20]
                
            elif messageType == '54': # Button Report
                # 02 54
                # 1 byte button event
                # 02 = set button tapped
                # 03 = Set button press and hold >3 seconds
                # 04 = Set button released after Set button press and hold event (03)
                # 12 = button 2 was tapped
                # 13 = Button 2 Press and Hold >3 seconds
                # 14 = Button 2 released after Press and Hold Event (13)
                # 22 = button 3 was tapped
                # 23 = Button 3 press and hold >3 seconds
                # 24 = button 3 released after press and hold event (23)

                msgButtonEvent = message[4:6]
                
            elif messageType == '55': # User Reset detected
                # 02 55
                pass
            elif messageType == '56': # All-Link Cleanup Failure
                # 02 56
                # 01 (hard coded, indicates this all link group member did not acknowledge an all-link cleanup command
                # 1 byte all link group
                # 3 byte ID of device not responding
                msgGroupID = message[6:8]
                msgFrom = message[8:14]
                
            elif messageType == '57': # All-Link Record Reponse
                # 02 57
                # 1 byte All-Link Record flags
                    # bit 7 Record in use (always will be 1)
                    # bit 6 1=IM controller, 1=IM Responder
                    # bit 5 product dependent (i believe in some devices this is the hop count)
                    # bit 4 product dependent
                    # bit 2-3 reserved (set to 0)
                    # bit 1 high water mark (will always be 1)
                    # bit 0 reserved (set to 0)
                # 3 bytes ID of device
                # 3 bytes link data

                msgLinkFlags = message[4:6]
                msgGroupID = message[6:8]
                msgLinkAddress = message[8:14]
                msgLinkData1 = message[14:16]
                msgLinkData2 = message[16:18]
                msgLinkData3 = message[18:20]
                
            elif messageType == '58': # All-Link Cleanup Status Report
                # 02 58
                # 1 byte status (06 success, 15 NAK)
                msgStatus = message[4:6] 
            else:
                print("Unknown messageType received: %s\n" % messageType)
            
            

            return messageLength


                
        

def main(p):
    while True:
        x = str(input("input C to quit: "))
        if x == 'C':
            break;

        time.sleep(0.1)

    p.running = False
    return

def bottleHost(plm):
    api = camacho_api.CamachoAPI(plm,'localhost',8080)
    api.start()
 
plm = PLM('\\\\.\\COM8')

writerThread = threading.Thread(target=plm.processSendBuffer)
readerThread = threading.Thread(target=plm.processReceiveBuffer)

writerThread.start()
readerThread.start()

#mainThread = threading.Thread(target=main, args=(plm,))
bottleThread = threading.Thread(target=bottleHost, args=(plm,))
bottleThread.start()
#mainThread.start()
#mainThread.join()
readerThread.join()
bottleThread.join()
writerThread.join()
    

##
##address = sys.argv[1]
##command = sys.argv[2]
##
##str = '0262' + address
##if command == 'on':
##    str += '0311FF'
##elif command == 'off':
##    str += '031300'
##elif command == 'link':
##    str += '1F090100000000000000000000000000F6'
##elif command == 'set':
##    str = '02640300'
##else:
##    sys.exit(2)

##str = '02640300'
##
##print(str)
##packet = base64.b16decode(str)
##
##port = serial.Serial('\\\\.\\COM8', 19200, timeout=2)
##port.write(packet)
##packet = port.read(100)
##port.close()
##
##str = base64.b16encode(packet)
##print(str)
