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
import numpy as np

### Maybe should add argcomplete for this program?


# Command-line arguments: computer settings
# Command-line arguments: computer settings
parser = argparse.ArgumentParser(description='Run simple linear track experiment.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyACM0',
                   help='TTY device for USB-serial interface (e.g., /dev/ttyUSB0 or COM10)')
parser.add_argument('--param-file', default='defaults.yaml',  
                    help='YAML file containing task parameters')
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

cmd_log_filename = '{}{}.txt'.format('CommandLog', now.strftime("%Y-%m-%d %H%M"))
cmd_log_filename = os.path.join(args.output_dir, cmd_log_filename)



# YAML parameters: task settings
with open(args.param_file, 'r') as f:
    Config = yaml.safe_load(f)

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


#----------------------- parameters --------------
TrackTransform = None

if Config['Maze']['Type'] != 'StateMachine':
    raise(NotImplementedError("Don't use this script for a VR"))


from SoundStimulus import SoundStimulus

BackgroundSounds = {}
Beeps = {}

for stimulus_name, stimulus in StimuliList.items():
    filename = stimulus['Filename']
    if Config['Preferences']['AudioFileDirectory']:
        filename = os.path.join(Config['Preferences']['AudioFileDirectory'], filename)
    print('Loading: {}'.format(filename))

    if stimulus['Type'] == 'Background':
        pass
        #BackgroundSounds[stimulus_name] = SoundStimulus(filename=filename)
        #BackgroundSounds[stimulus_name].change_gain(stimulus['BaselineGain'])
    elif stimulus['Type'] == 'Beep':
        Beeps[stimulus_name] = None
        #Beeps[stimulus_name] = SoundStimulus(filename=filename)
        #Beeps[stimulus_name].change_gain(stimulus['BaselineGain'])
        #Beeps[stimulus_name].change_gain(-90.0) # beep for a very short moment
    elif stimulus['Type'] == 'Localized':
        raise(NotImplementedError("Localized auditory stimuli not supported for StateMachine control script."))

    time.sleep(1.0)


from SerialInterface import SerialInterface

Interface = SerialInterface(SerialPort=args.serial_port)

if 'GPIO' in Config:
    for gpio_label, gpio_config in Config['GPIO'].items():
        Interface.add_gpio(gpio_label, gpio_config)


from TaskStateMachine import DelayState, RewardState, VisualizationState

StateMachineDict = {}
FirstState = None
for state_name, state in Config['StateMachine'].items():
    if 'FirstState' in state and state['FirstState']:
        FirstState = state_name

    if (state['Type'] == 'Delay'):
        StateMachineDict[state_name] = DelayState(state_name, state['NextState'], state['Params'])
    elif (state['Type'] == 'Reward'):
        if state['Params']['DispensePin'] not in Interface.GPIOs:
            raise ValueError('Dispense pin not in defined GPIO list')
        if state['Params']['RewardSound'] != 'None':
            if state['Params']['RewardSound'] not in Beeps:
                raise ValueError('Reward sound not in defined Beeps list')
        StateMachineDict[state_name] = RewardState(state_name, state['NextState'], state['Params'])
    elif (state['Type'] == 'Visualization'):
        StateMachineDict[state_name] = VisualizationState(state_name, state['NextState'], state['Params'])
    else:
        raise(NotImplementedError("State machine elements other than " 
                "Delay, Reward, or Visualization not yet implemented"))

if FirstState is None:
    FirstState = list(StateMachineDict.keys())[0]
    print('First state in state machine not defined. '
          'Picking first state in list: {}'.format(FirstState))
else:
    print('First state is {}'.format(FirstState))


import zmq

context = zmq.Context()
socket = context.socket(zmq.PAIR)
if 'VisualCommsPort' in Config['Preferences']:
    port = str(Config['Preferences']['VisualCommsPort'])
else:
    port = "5556"


#log_file = open(log_filename, 'w', newline='')
#cmd_log_file = open(cmd_log_filename, 'w', newline='')

with open(log_filename, 'w', newline='') as log_file, \
     open(cmd_log_filename, 'w', newline='') as cmd_log_file, \
     context.socket(zmq.PAIR) as socket:

    socket.connect("tcp://localhost:%s" % port)

    Interface.connect()

    ## initiate encoder value ##
    #FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO = Interface.read_data()
    FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()

    RewardPumpEndTime = 0
    RewardPumpActive = False

    StateMachineWaiting = False
    StateMachineWaitEndTime = 0

    CurrentState = StateMachineDict[FirstState]
    if (CurrentState.Type == 'Delay'):
        StateMachineWaitEndTime = MasterTime + CurrentState.getDelay()
        StateMachineWaiting = True

    writer = csv.writer(log_file)
    cmd_writer = csv.writer(cmd_log_file)

    while(True):
        ## every 2 ms happens:
        last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
        #FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO = Interface.read_data()
        FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()


        writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts])

        TrackPosition = 0 

        if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
            print('Heartbeat {} - {} - 0x{:08b}'.format(MasterTime, TrackPosition, GPIO))


        # StateMachine

        if StateMachineWaiting:
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
                cmd_writer.writerow(['Delay', MasterTime, delay])
            elif CurrentState.Type == 'Reward':
                RewardPin, PulseLength, RewardSound = CurrentState.rewardValues()
                RewardPumpActive = True
                RewardPumpEndTime = MasterTime + PulseLength
                Interface.raise_output(RewardPin)
                #if RewardSound:
                #    Beeps[RewardSound].change_gain(stimulus['BaselineGain'])
                print('Reward!')
                cmd_writer.writerow(['Reward', MasterTime])
                CurrentState = StateMachineDict[CurrentState.NextState]
            elif (CurrentState.Type == 'Visualization'):
                command = CurrentState.getVisualizationCommand()
                cmd_writer.writerow([command, MasterTime])
                print(command)
                socket.send_string(command)
                CurrentState = StateMachineDict[CurrentState.NextState]


        # Reward
        if RewardPumpActive:
            if MasterTime > RewardPumpEndTime:
                RewardPumpActive = False
                Interface.lower_output(RewardPin)
                print('Rewad off')
                #if RewardSound:
                #    Beeps[RewardSound].change_gain(-90.0)




