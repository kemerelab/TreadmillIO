#!/usr/bin/env python

#%%
# NOTE: v2.1.1. 3 different Tones (3kHz, 6kHz, 12kHz) are played based on animal's position on the virtual track. 
#       ramping volume depend on a parameter named "peak_volume" describing how steep the ramping function
#       should be (default 13). Taking care the max peakVolume or OnVolume should not exceed -90dB and 90dB.
# Features: 
#     sound logic that is controlled only by linear_pos
#     pump logic controlled by PumpOn and PumpOffTime, so each time the pump is triggered, it must reset after 100ms regardless of animal's pos
#     peak_volume is constant number regardless of different tone frequencies
#     max_reward_times controls the max number of reward it can get within one single lap
#
#  See SoundStimulus.py - need to run `jackd -R -P50 -v -d alsa -p64 -n2 -P hw:1,0 -r48000` (use aplay -l/-L to figure out which hw device)
#

import time
import datetime
import os
import argparse
import yaml
import csv
import zmq
import numpy as np
import warnings

from contextlib import ExitStack


NamedVersion = '1.0'


import git
repo = git.Repo(search_parent_directories=True)

GitCommit = repo.head.object.hexsha
GitChangedFiles = [fn.a_path for fn in repo.index.diff(None)]
GitPatch = [fn.diff for fn in repo.index.diff(None, create_patch=True)]

### Maybe should add argcomplete for this program?

# Command-line arguments: computer settings
# Command-line arguments: computer settings
parser = argparse.ArgumentParser(description='Run simple linear track experiment.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyACM0',
                   help='TTY device for USB-serial interface (e.g., /dev/ttyUSB0 or COM10)')
parser.add_argument('-C','--param-file', default='defaults.yaml',  
                    help='YAML file containing task parameters')
parser.add_argument('-R','--random-seed', default=None,  
                    help='Random seed. If specified, this also overrides the YAML configuration file.')
parser.add_argument('--output-dir', default='./',
                    help='Directory to write output file (defaults to cwd)')
parser.add_argument('--output-file', default='chart.pdf',
                    help="Name for the rendered statemachine chart file (defaults to 'chart.pdf')")
args = parser.parse_args()
if not os.path.isdir(args.output_dir):
    os.mkdir(args.output_dir)
if not args.output_dir.endswith('/'):
    args.output_dir += '/'
print(args)

now = datetime.datetime.now()
log_filename = '{}{}.txt'.format('Log', now.strftime("%Y-%m-%d %H%M"))
log_filename = os.path.join(args.output_dir, log_filename)

# YAML parameters: task settings
with open(args.param_file, 'r') as f:
    Config = yaml.safe_load(f)

DoLogCommands = False
if 'LogCommands' in Config['Preferences']:
    DoLogCommands = Config['Preferences']['LogCommands']

EnableSound = False
if 'EnableSound' in Config['Preferences']:
    EnableSound = Config['Preferences']['EnableSound']

# Check for random seed on command line or in preferences
if args.random_seed is not None:
    np.random.seed(int(args.random_seed))
    print(f'Setting random seed to {args.random_seed}.')
    if 'RandomSeed' in Config['Preferences']:
        Config['Preferences']['RandomSeed'] = int(args.random_seed)
        print('Overwriting random seed in preferences file (true value will be logged).')
elif 'RandomSeed' in Config['Preferences']:
    np.random.seed(Config['Preferences']['RandomSeed'])
    print(f"Setting random seed to {Config['Preferences']['RandomSeed']}.")



#----------------------- parameters --------------
TrackTransform = None

virtual_track_length = 1000.0 #cm
d = 20.2 #cm
encoder_gain = 4096.0
if 'Maze' in Config:
    if 'Length' in Config['Maze']:
        virtual_track_length = Config['Maze']['Length'] #cm
    if 'Diameter' in Config['Maze']:
        d = Config['Maze']['WheelDiameter'] #cm diameter of the physical wheel; 150cm
    if 'EncoderGain' in Config['Maze']:
        encoder_gain = Config['Maze']['EncoderGain']

#----------------------- Sound stimuli --------------

from treadmillio.soundstimulus import SoundStimulusController

with ExitStack() as stack:
    if 'AuditoryStimuli' in Config and EnableSound:
        SoundController = stack.enter_context(SoundStimulusController(Config['AuditoryStimuli'], virtual_track_length))
    else:
        SoundController = None
        if 'AuditoryStimuli' in Config:
            warnings.warn("Config file specified AuditoryStimuli, but EnableSound is False.", RuntimeWarning)

    # --------------  Initialize Serial IO - Won't actually do anything until we call connect()! --------------------------
    from treadmillio import SerialInterface

    if 'GPIO' in Config:
        Interface = stack.enter_context(SerialInterface(SerialPort=args.serial_port, config=Config['GPIO']))
    else:
        Interface = stack.enter_context(SerialInterface(SerialPort=args.serial_port, config=None))
        warnings.warn("No GPIOs specified in config file. All IOs will be inputs.", RuntimeWarning)

    # ------------------- Read in State Machine States. ------------------------------------------------------------------
    if 'StateMachine' in Config:
        from treadmillio.taskstatemachine import TaskStateMachine

        # BUG: Should check to make sure states are all connected properly?
        StateMachine = stack.enter_context(TaskStateMachine(Config['StateMachine'], Interface, SoundController))
    else:
        StateMachine = None

    # ------------------- Read in VR Reward Zones. ------------------------------------------------------------------
    if 'RewardZones' in Config:
        from treadmillio.rewardzone import RewardZoneController

        RewardZones = RewardZoneController(Config['RewardZones'], Interface, SoundController)

    else:
        RewardZones = None

    # -------------------------- Start logging and stimulus connection -------------------------------------
    #log_file = stack.enter_context(open(log_filename, 'w', newline=''))

    StateMachine.render(args.output_file)