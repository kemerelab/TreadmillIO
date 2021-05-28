import zmq
import sys
import time
import pickle

if len(sys.argv) > 1:
    port = int(sys.argv[1])
else:
    port = 7910

context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.bind("tcp://*:%s" % port)

config = {
    "ConfigDevice": True, 
    "HWDevice": "hw:CARD=sofhdadsp,DEV=0",
    "SamplingRate": 48000
}

stimuli = {
    "LoadStimuli": True,
    "tonecloud": {
        "Filename": "/home/ckemere/Code/TreadmillIO/ClientSide/Sounds/48kHz/tone_cloud_short.wav",
        "Channel": 0}
}

socket.send(pickle.dumps(config))
msg = socket.recv()
print(msg)
if msg != b"ConfigSuccess":
    exit(-1)
socket.send(pickle.dumps(stimuli))
msg = socket.recv()
print(msg)
if msg != b"LoadSuccess":
    exit(-1)
socket.send(pickle.dumps({"Run":True}))
msg = socket.recv()
print(msg)
if msg != b"Running":
    exit(-1)
print('Sending volume')
socket.send(pickle.dumps({"tonecloud":1.0}))
time.sleep(5)
socket.send(pickle.dumps({"Stop":True}))
msg = socket.recv()
print(msg)
if msg != b"Stopped":
    exit(-1)
socket.send(pickle.dumps({"Exit":True}))
msg = socket.recv()
print(msg)
if msg != b"Exiting":
    exit(-1)

print("All done!")

while True:
    pass
exit(0)
