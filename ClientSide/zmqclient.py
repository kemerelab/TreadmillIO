import zmq
import random
import sys
import time

port = "5556"
context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.connect("tcp://localhost:%s" % port)

command = sys.argv[1]
print(command)

#while True:
socket.send_string(command)


