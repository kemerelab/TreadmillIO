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


if Config['Maze']['Type'] != 'StateMachine':
    raise(NotImplementedError("Don't use this script for a VR"))

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

#----------------------- Sound stimuli --------------
if EnableSound:
    print('Normalizing stimuli:')
    StimuliList = Config['AuditoryStimuli']['StimuliList']
    for stimulus_name, stimulus in StimuliList.items(): 
        print(' - ',stimulus_name)
        for key, config_item in Config['AuditoryStimuli']['Defaults'].items():
            if key not in stimulus:
                stimulus[key] = config_item
            elif isinstance(config_item, dict):
                for subkey, sub_config_item in config_item.items():
                    if subkey not in stimulus[key]:
                        stimulus[key][subkey] = sub_config_item


if EnableSound:
    from SoundStimulus import SoundStimulus

    BackgroundSounds = {}
    Beeps = {}

    for stimulus_name, stimulus in StimuliList.items():
        filename = stimulus['Filename']
        if Config['Preferences']['AudioFileDirectory']:
            filename = os.path.join(Config['Preferences']['AudioFileDirectory'], filename)
        print('Loading: {}'.format(filename))

        if stimulus['Type'] == 'Background':
            BackgroundSounds[stimulus_name] = SoundStimulus(filename=filename)
            BackgroundSounds[stimulus_name].change_gain(stimulus['BaselineGain'])
        elif stimulus['Type'] == 'Beep':
            Beeps[stimulus_name] = SoundStimulus(filename=filename)
            Beeps[stimulus_name].change_gain(stimulus['BaselineGain'])
            Beeps[stimulus_name].change_gain(-90.0) # beep for a very short moment
        elif stimulus['Type'] == 'Localized':
            raise(NotImplementedError("Localized auditory stimuli not supported for StateMachine control script."))

        time.sleep(1.0)


# --------------  Initialize Serial IO - Won't actually do anything until we call connect()! --------------------------
from SerialInterface import SerialInterface

Interface = SerialInterface(SerialPort=args.serial_port)

if 'GPIO' in Config:
    for gpio_label, gpio_config in Config['GPIO'].items():
        Interface.add_gpio(gpio_label, gpio_config)


# ------------------- Read in State Machine States. ------------------------------------------------------------------

from TaskStateMachine import DelayState, RewardState, VisualizationState, SetGPIOState

StateMachineDict = {}
FirstState = None
for state_name, state in Config['StateMachine'].items():
    if 'FirstState' in state and state['FirstState']:
        FirstState = state_name

    if (state['Type'] == 'Delay'):
        StateMachineDict[state_name] = DelayState(state_name, state['NextState'], state['Params'])

    elif (state['Type'] == 'SetGPIO'):
        if state['Params']['Pin'] not in Interface.GPIOs:
            raise ValueError('GPIO pin not in defined GPIO list')
        StateMachineDict[state_name] = SetGPIOState(state_name, state['NextState'], state['Params'])

    elif (state['Type'] == 'Reward'):
        if state['Params']['DispensePin'] not in Interface.GPIOs:
            raise ValueError('Dispense pin not in defined GPIO list')
        if EnableSound and state['Params']['RewardSound'] != 'None':
            if state['Params']['RewardSound'] not in Beeps:
                raise ValueError('Reward sound not in defined Beeps list')
        StateMachineDict[state_name] = RewardState(state_name, state['NextState'], state['Params'])

    elif (state['Type'] == 'Visualization'):
        StateMachineDict[state_name] = VisualizationState(state_name, state['NextState'], state['Params'])

    else:
        raise(NotImplementedError("State machine elements other than " 
                "Delay, SetGPIO, Reward, or Visualization not yet implemented"))

if FirstState is None:
    FirstState = list(StateMachineDict.keys())[0]
    print('First state in state machine not defined. '
          'Picking first state in list: {}'.format(FirstState))
else:
    print('First state is {}'.format(FirstState))

# BUG: Should check to make sure states are all connected properly?

# ----------------------- Initialize communications to VisualStimulusServer ---------------------------
context = zmq.Context()
socket = context.socket(zmq.PAIR)
if 'VisualCommsPort' in Config['Preferences']:
    port = str(Config['Preferences']['VisualCommsPort'])
else:
    port = "5556"



# -------------------------- Start logging and stimulus connection -------------------------------------
with open(log_filename, 'w', newline='') as log_file, \
     context.socket(zmq.PAIR) as socket:

    socket.connect("tcp://localhost:%s" % port)


    ##### Write header to log file
    print(f'VisualStimulusExperiment Data File.\n   Version {NamedVersion}',file=log_file)
    print(f'   Git Commit: {GitCommit}',file=log_file)
    if GitChangedFiles:
        print(f'   ChangedFiles: {GitChangedFiles}',file=log_file)
        print(f'Patch:\n{GitPatch}',file=log_file)
    print('---',file=log_file)
    yaml.dump(Config, log_file, indent=4)
    print('---\n', file=log_file)

    ##### Logging is actually CSV format
    writer = csv.writer(log_file)

    # ----------------- Initialization
    RewardPumpEndTime = 0
    RewardPumpActive = False

    StateMachineWaiting = False
    StateMachineWaitEndTime = 0

    CurrentState = StateMachineDict[FirstState]

    ##### Actually connect to IO device. We wait until here so that data doesn't get lost/confused in serial buffer
    Interface.connect()

    FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()

    if (CurrentState.Type == 'Delay'):
        StateMachineWaitEndTime = MasterTime + CurrentState.getDelay()
        StateMachineWaiting = True

    while(True):
        ## every 2 ms happens:
        FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()
        last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
                                     # since read_data() is blocking, this is a farther bound (i.e., ts AFTER) data

        writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts]) # Log data from serial interface

        if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
            print(f'Heartbeat {MasterTime} - 0x{GPIO:012b}')

        # -------------------- StateMachine -------------------- 

        if StateMachineWaiting: # Currently in a `Delay` or other state in which we shouldn't transition yet
            if MasterTime > StateMachineWaitEndTime:
                CurrentState = StateMachineDict[CurrentState.NextState]
                StateMachineWaiting = False
            else:
                pass
        else:
            if CurrentState.Type == 'Delay':
                delay = CurrentState.getDelay()
                StateMachineWaitEndTime = MasterTime + delay
                StateMachineWaiting = True
                if DoLogCommands:
                    writer.writerow([MasterTime,-1,-1,-1,-1,'Delay', delay])

            elif CurrentState.Type == 'SetGPIO':
                Pin, Value = CurrentState.getPinValue()
                if Value:
                    Interface.raise_output(Pin)
                else:
                    Interface.lower_output(Pin)
                if DoLogCommands:
                    writer.writerow([MasterTime,-1,-1,-1,-1,'SetGPIO', Pin, Value])
                CurrentState = StateMachineDict[CurrentState.NextState]

            elif CurrentState.Type == 'Reward':
                RewardPin, PulseLength, RewardSound = CurrentState.rewardValues()
                RewardPumpActive = True
                RewardPumpEndTime = MasterTime + PulseLength
                Interface.raise_output(RewardPin)
                if EnableSound and RewardSound:
                    Beeps[RewardSound].change_gain(stimulus['BaselineGain'])
                #print('Reward!')
                if DoLogCommands:
                    writer.writerow([MasterTime,-1,-1,-1,-1,'Reward', RewardPin, PulseLength])
                CurrentState = StateMachineDict[CurrentState.NextState]
                
            elif (CurrentState.Type == 'Visualization'):
                command = CurrentState.getVisualizationCommand()
                #print(command)
                if DoLogCommands:
                    writer.writerow([MasterTime,-1,-1,-1,-1,'Visualization', command])                
                socket.send_string(command)
                CurrentState = StateMachineDict[CurrentState.NextState]

        # Reward
        if RewardPumpActive:
            if MasterTime > RewardPumpEndTime:
                RewardPumpActive = False
                Interface.lower_output(RewardPin)
                if EnableSound and RewardSound:
                    Beeps[RewardSound].change_gain(-90.0)




