from psychopy import visual, core, event, monitors
import numpy as np

import zmq
import random
import sys
import time
import math


USE_BLUE = True # CHANGE THIS TO FALSE TO USE Black/White instead of Black/Blue

CS = 'rgb'  # ColorSpace
WHITE = [1, 1, 1]
LIGHT_GREY = [0.5, 0.5, 0.5]
GREY = [0, 0, 0]
BLACK = [-1, -1, -1]
BLUE_GREY = [-1, -1, -0.5]
BLUE =[-1, -1, 1]

## ---- Comment this section in to try a different colorspace
# CS = 'rgb255'  # ColorSpace
# WHITE = [255, 255, 255]
# LIGHT_GREY = [200, 200, 200]
# GREY = [128, 128, 128]
# BLACK = [0, 0, 0]


ScreenSize = [640,480]
#ScreenSize = [1920, 1080]
#ScreenSize = [1024,768]
#ScreenSize = [3840,1080]

MonitorWidth = 16.0 # cm
MouseDistance = 10.0 # cm

SmallMonitor = monitors.Monitor('SmallMonitor', distance=MouseDistance)
SmallMonitor.setSizePix(ScreenSize)
SmallMonitor.setWidth(MonitorWidth)

if USE_BLUE:
    color = BLUE_GREY
else:
    color = GREY

win_left = visual.Window(ScreenSize, monitor=SmallMonitor,
                    color=color, colorSpace=CS,
                    allowGUI=False,
                    screen=2, fullScr=True,
                    units='pix')

win_center = visual.Window(ScreenSize, monitor=SmallMonitor,
                    color=color, colorSpace=CS,
                    allowGUI=False,
                    screen=1, fullScr=True,
                    units='pix')

win_right = visual.Window(ScreenSize, monitor=SmallMonitor,
                    color=color, colorSpace=CS,
                    allowGUI=False,
                    screen=3, fullScr=True,
                    units='pix')



if USE_BLUE:
    img1 = np.tile(np.array([[BLACK, BLUE], [BLUE, BLACK]]), (4,3,1)) # Checkerboard bitmap 10x10 cell
    img2 = np.tile(np.array([[BLUE, BLACK], [BLACK, BLUE]]), (4,3,1)) # Opposite phase
else:
    img1 = np.tile(np.array([[-1, 1], [1, -1]]), (4,3)) # Checkerboard bitmap
    img2 = np.tile(np.array([[1, -1], [-1, 1]]), (4,3)) # Opposite phase



# ADD CENTER STIMULUS!!!
stimulus_center1 = visual.ImageStim(win=win_center, image=img1, colorSpace=CS, color=WHITE,
                     size=(MonitorWidth, MonitorWidth*3/4), # assume 4:3 aspect ratio
                     pos=(0, 0), # centered
                     units='cm')

stimulus_center2 = visual.ImageStim(win=win_center, image=img2, colorSpace=CS, color=WHITE,
                     size=(MonitorWidth, MonitorWidth*3/4),
                     pos=(0, 0), # centered
                     units='cm')

stimulus_left1 = visual.ImageStim(win=win_left, image=img1, colorSpace=CS, color=WHITE,
                     size=(MonitorWidth, MonitorWidth*3/4),
                     pos=(0, 0), # monitor width / 2 = left edge
                     units='cm')

stimulus_left2 = visual.ImageStim(win=win_left, image=img2, colorSpace=CS, color=WHITE,
                     size=(MonitorWidth, MonitorWidth*3/4), 
                     pos=(0, 0), # monitor width / 2 = left edge
                     units='cm')

stimulus_right1 = visual.ImageStim(win=win_right, image=img1, colorSpace=CS, color=WHITE,
                     size=(MonitorWidth, MonitorWidth*3/4), 
                     pos=(0, 0), # monitor width / 2 = left edge
                     units='cm')

stimulus_right2 = visual.ImageStim(win=win_right, image=img2, colorSpace=CS, color=WHITE,
                     size=(MonitorWidth, MonitorWidth*3/4), 
                     pos=(0, 0), # monitor width / 2 = left edge
                     units='cm')


def animateStimulus(t, stimulus1, stimulus2, rate):
    if np.mod(t*2*rate, 2) < 1.0:
        stimulus1.draw()
    else:
        stimulus2.draw()
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

flashing_rate = 8.0

while True:
    t = trialClock.getTime()

    if state != 'GRAY':
        if (t < tend):
            if state =='LEFT':
                animateStimulus(t - tstart, stimulus_left1, stimulus_left2, rate=flashing_rate)
            elif state == 'RIGHT':
                animateStimulus(t - tstart, stimulus_right1, stimulus_right2, rate=flashing_rate)
            elif state == 'CENTER':
                animateStimulus(t - tstart, stimulus_center1, stimulus_center2, rate=flashing_rate)
            elif state == 'BOTH':
                animateStimulus(t - tstart, stimulus_left1, stimulus_left2, rate=flashing_rate)
                animateStimulus(t - tstart, stimulus_right1, stimulus_right2, rate=flashing_rate)
        else:
            state = 'GRAY'

    win_center.flip()          #update the screen
    win_left.flip()          #update the screen
    win_right.flip()          #update the screen


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
        elif zmq_command.upper() == "CENTER":
            state = 'CENTER'
            tstart = t
            tend = t + flash_duration
        elif zmq_command.upper() == "BOTH":
            state = 'BOTH'
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
        elif keys in ['c','C']:
            state = 'CENTER'
            tstart = t
            tend = t + flash_duration
        elif keys in ['b','B']:
            state = 'BOTH'
            tstart = t
            tend = t + flash_duration


