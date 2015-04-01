import sys
import time

class Device:
    def __init__(self,name,address):
        self.name=name
        self.address=address
        self.status = 0
