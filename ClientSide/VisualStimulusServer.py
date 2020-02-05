from psychopy import visual, core, event
import numpy as np

import zmq
import random
import sys
import time


CS = 'rgb'  # ColorSpace
WHITE = [1, 1, 1]
LIGHT_GREY = [0.5, 0.5, 0.5]
GREY = [0, 0, 0]
BLACK = [-1, -1, -1]

## ---- Comment this section in to try a different colorspace
# CS = 'rgb255'  # ColorSpace
# WHITE = [255, 255, 255]
# LIGHT_GREY = [200, 200, 200]
# GREY = [128, 128, 128]
# BLACK = [0, 0, 0]

win = visual.Window([1600, 1600], monitor='testMonitor',
                    color=LIGHT_GREY, colorSpace=CS,
                    units='pix')

img = np.tile(np.array([[-1, 1], [1, -1]]), (int(20/2), int(20/2))) # Image bitmap

stimulus_left = visual.ImageStim(win=win, image=img,
                     colorSpace=CS,
                     color=WHITE,
                     size=(400, 400),
                     pos=(-600, 0),
                     units='pix')

stimulus_right = visual.ImageStim(win=win, image=img,
                     colorSpace=CS,
                     color=WHITE,
                     size=(400, 400),
                     pos=(600,0),
                     units='pix')



def animateStimulus(t, stimulus, rate):
    if np.mod(t*2*rate, 2) < 1.0:
        stimulus.color = WHITE
        stimulus.draw()
    else:
        stimulus.color = BLACK
        stimulus.draw()
    return True

port = "5556"
context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.bind("tcp://*:%s" % port)
zmq_poller = zmq.Poller()
zmq_poller.register(socket, zmq.POLLIN)

trialClock = core.Clock()
t = 0
state = 'GRAY'
flash_duration = 2 # s
while True:
    t = trialClock.getTime()

    if state != 'GRAY':
        if (t < tend):
            if state =='LEFT':
                animateStimulus(t - tstart, stimulus_left, rate=40.0)
            elif state == 'RIGHT':
                animateStimulus(t - tstart, stimulus_right, rate=40.0)
        else:
            state = 'GRAY'

    win.flip()          #update the screen



    zmq_msgs = dict(zmq_poller.poll(timeout=0)) 
    if socket in zmq_msgs and zmq_msgs[socket] == zmq.POLLIN:
        zmq_command = socket.recv_string()
        if zmq_command.upper() in {"GREY","GRAY"}:
            state = 'GRAY'
        elif zmq_command.upper() == "LEFT":
            state = 'LEFT'
            tstart = t
            tend = t + flash_duration
        elif zmq_command.upper() == "RIGHT":
            state = 'RIGHT'
            tstart = t
            tend = t + flash_duration


    #handle key presses each frame
    for keys in event.getKeys():
        if keys in ['escape','q']:
            core.quit()
        elif keys in ['g', 'G']:
            state = 'GRAY'
        elif keys in ['l','L','left']:
            state = 'LEFT'
            tstart = t
            tend = t + flash_duration
        elif keys in ['r','R','right']:
            state = 'RIGHT'
            tstart = t
            tend = t + flash_duration


