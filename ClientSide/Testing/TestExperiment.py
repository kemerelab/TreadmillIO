import zmq
import random
import sys
import time

port = "5556"
context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.connect("tcp://localhost:%s" % port)

while True:
    time.sleep(5)
    socket.send_string('LEFT')
    time.sleep(5)
    socket.send_string('GREY')
    time.sleep(5)
    socket.send_string('RIGHT')
    time.sleep(5)
    socket.send_string('GREY')


