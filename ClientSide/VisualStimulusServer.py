from psychopy import visual, core, event, monitors
import numpy as np

import zmq
import random
import sys
import time
import math


CS = 'rgb'  # ColorSpace
WHITE = [1, 1, 1]
LIGHT_GREY = [0.5, 0.5, 0.5]
GREY = [0, 0, 0]
BLUE_GREY = [-1, -1, -0.5]
BLACK = [-1, -1, -1]
BLUE =[-1, -1, 1]

## ---- Comment this section in to try a different colorspace
# CS = 'rgb255'  # ColorSpace
# WHITE = [255, 255, 255]
# LIGHT_GREY = [200, 200, 200]
# GREY = [128, 128, 128]
# BLACK = [0, 0, 0]


BigMonitor = monitors.Monitor('CurvedSamsung46', distance=20)
# BigMonitor.setSizePix([1920, 1080])
BigMonitor.setSizePix([3840, 1080])
BigMonitor.setWidth(117)


win = visual.Window([3840,1080], monitor=BigMonitor,
                    color=BLUE_GREY, colorSpace=CS,
                    allowGUI=False,
                    screen=1, fullScr=True,
                    units='pix')

MonitorWidth = 117.0 # cm
MouseDistance = 20.0 # cm
CenterEmpty = 60.0 # degrees
EdgeOfStimulus = math.tan(CenterEmpty/2 / 180 * math.pi) * MouseDistance
HalfWidthOfStimulus = MonitorWidth/2 - EdgeOfStimulus
StimulusWidth = HalfWidthOfStimulus * 2


img1 = np.tile(np.array([[BLACK, BLUE], [BLUE, BLACK]]), (10,10,1)) # Image bitmap
img2 = np.tile(np.array([[BLUE, BLACK], [BLACK, BLUE]]), (10,10,1)) # Image bitmap

# ADD CENTER STIMULUS!!!

stimulus_left = visual.ImageStim(win=win, image=img,
                     colorSpace=CS,
                     color=WHITE,
                     size=(StimulusWidth, StimulusWidth), # leave a 60 deg wid
                     pos=(-MonitorWidth/2, 0), # monitor width / 2 = left edge
                     units='cm')

stimulus_right = visual.ImageStim(win=win, image=img,
                     colorSpace=CS,
                     color=WHITE,
                     size=(StimulusWidth, StimulusWidth), # leave a 60 deg wid
                     pos=(MonitorWidth/2, 0), # monitor width / 2 = left edge
                     units='cm')



def animateStimulus(t, stimulus, rate):
    if np.mod(t*2*rate, 2) < 1.0:
      # stimulus.color = WHITE
        stimulus.setImage(img1)
        stimulus.draw()
    else:
      # stimulus.color = BLACK
        stimulus.setImage(img2)
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
flash_duration = 100 # s
while True:
    t = trialClock.getTime()

    if state != 'GRAY':
        if (t < tend):
            if state =='LEFT':
                animateStimulus(t - tstart, stimulus_left, rate=8.0)
            elif state == 'RIGHT':
                animateStimulus(t - tstart, stimulus_right, rate=8.0)
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


