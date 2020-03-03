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

# GPIO IDs on IO board
GPIO_IDs = [16, 17, 18, 19, 24, 25, 26, 27, -1]

# Command-line arguments: computer settings
# Command-line arguments: computer settings
parser = argparse.ArgumentParser(description='Run simple linear track experiment.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyS0',
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

if Config['Maze']['Type'] == 'VR':
    VirtualTrackLength = Config['Maze']['Length'] #cm
    d = Config['Maze']['WheelDiameter'] #cm diameter of the physical wheel; 150cm
count = 0


#%%
from RenderTrack import RenderTrack

visualization = RenderTrack(track_length=VirtualTrackLength)

from SoundStimulus import SoundStimulus

BackgroundSounds = {}
Beeps = {}
SoundStimuliList = {}

for stimulus_name, stimulus in StimuliList.items():

    filename = stimulus['Filename']
    if Config['Preferences']['AudioFileDirectory']:
        filename = os.path.join(Config['Preferences']['AudioFileDirectory'], filename)
    print('Loading: {}'.format(filename))

    if stimulus['Type'] == 'Background':
        BackgroundSounds[stimulus_name] = SoundStimulus(filename=filename)
        visualization.add_zone_position(0, VirtualTrackLength, fillcolor=stimulus['Color'], width=0.5, alpha=0.75)
        BackgroundSounds[stimulus_name].change_gain(stimulus['BaselineGain'])
    elif stimulus['Type'] == 'Beep':
        Beeps[stimulus_name] = SoundStimulus(filename=filename)
        Beeps[stimulus_name].change_gain(stimulus['BaselineGain'])
        Beeps[stimulus_name].change_gain(-90.0) # beep for a very short moment
    elif stimulus['Type'] == 'Localized':
        SoundStimuliList[stimulus_name] = SoundStimulus(filename=filename)
        visualization.add_zone_position(stimulus['CenterPosition'] - stimulus['Modulation']['Width']/2, 
                               stimulus['CenterPosition'] + stimulus['Modulation']['Width']/2, 
                               fillcolor=stimulus['Color'])

        SoundStimuliList[stimulus_name].initLocalizedSound(center=stimulus['CenterPosition'], 
                        width=stimulus['Modulation']['Width'], trackLength=VirtualTrackLength, 
                        maxGain=stimulus['BaselineGain'], minGain=stimulus['Modulation']['CutoffGain'])
        SoundStimuliList[stimulus_name].change_gain(-90.0) # start off turned off

    time.sleep(1.0)


from SerialInterface import SerialInterface

Interface = SerialInterface(SerialPort=args.serial_port)

if 'GPIO' in Config:
    for gpio_label, gpio_config in Config['GPIO'].items():
        Interface.add_gpio(gpio_label, gpio_config)


# Create a GPIO pin to use to trigger the lick sensor
Interface.add_gpio('LickTrigger',{'Number':1,'Type':'Output', 'Mirror':True})


from RewardZone import ClassicalRewardZone, OperantRewardZone

RewardsList = []
for reward_name, reward in Config['RewardZones']['RewardZoneList'].items():
    if (reward['Type'] == 'Classical') | (reward['Type'] == 'Operant'):
        if reward['DispensePin'] not in Interface.GPIOs:
            raise ValueError('Dispense pin not in defined GPIO list')

        if reward['RewardSound'] != 'None':
            if reward['RewardSound'] not in Beeps:
                raise ValueError('Reward sound not in defined Beeps list')


        visualization.add_zone_position(reward['RewardZoneStart'], reward['RewardZoneEnd'], 
                        fillcolor=None, edgecolor=reward['Color'], hatch='....', width=1.33, alpha=1.0)

        if (reward['Type'] == 'Classical'):
            RewardsList.append(ClassicalRewardZone((reward['RewardZoneStart'], reward['RewardZoneEnd']),
                    reward['DispensePin'], reward['PumpRunTime'], reward['RewardSound'],
                    reward['LickTimeout'],
                    reward['MaxSequentialRewards'], (reward['ResetZoneStart'], reward['ResetZoneEnd'])) )

        elif (reward['Type'] == 'Operant'):
            if reward['LickPin'] not in Interface.GPIOs:
                raise ValueError('Lick pin not in defined GPIO list')
            lickPinNumber = Interface.GPIOs[reward['LickPin']]['Number'] # We are going to bit mask raw GPIO for this

            RewardsList.append(OperantRewardZone((reward['RewardZoneStart'], reward['RewardZoneEnd']),
                    lickPinNumber, reward['DispensePin'], reward['PumpRunTime'], reward['RewardSound'],
                    reward['LickTimeout'],
                    reward['MaxSequentialRewards'], 
                    (reward['ResetZoneStart'], reward['ResetZoneEnd'])) )            
    else:
        raise(NotImplementedError("Reward types other than classical are not yet implemented"))




Interface.connect()

## initiate encoder value ##
#FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO = Interface.read_data()
FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()

initialUnwrappedencoder = UnwrappedEncoder 
print("initial unwrapped encoder value : ", UnwrappedEncoder)

RewardPumpEndTime = 0
RewardPumpActive = False

with open(log_filename, 'w', newline='') as log_file:
    writer = csv.writer(log_file)

    while(True):
        ## every 2 ms happens:
        last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
        #FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO = Interface.read_data()
        FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()


        writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts])

        if Config['Maze']['Type'] == 'VR':
            UnwrappedPosition = (UnwrappedEncoder - initialUnwrappedencoder) / Config['Maze']['EncoderGain'] *d *np.pi 
            TrackPosition = UnwrappedPosition % VirtualTrackLength
        else:
            # GPIO to Position transformation
            # Use this for controlling behavior on a physical track where position is not tracked by a rotary encoder
            # TrackPosition = TrackTransform.convert(GPIO[0])
            TrackPosition = 0 

        if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
            print('Heartbeat {} - {} - 0x{:08b}'.format(MasterTime, TrackPosition, GPIO))


            # Stimulus
            for _, sound in SoundStimuliList.items():
                sound.pos_update_gain(TrackPosition)

        if (MasterTime % 1000) == 0:
            Interface.raise_output('LickTrigger')

        if (MasterTime % 1000) == 50:
            Interface.lower_output('LickTrigger')


        # Reward
        if RewardPumpActive:
            if MasterTime > RewardPumpEndTime:
                RewardPumpActive = False
                Interface.lower_output(RewardPin)
                if RewardSound:
                    Beeps[RewardSound].change_gain(-90.0)

        if not RewardPumpActive: # Only check for reward if we're not rewarding
            for reward in RewardsList:
                reward_values = reward.pos_reward(TrackPosition, GPIO, MasterTime)
                if (reward_values):
                    RewardPin, PulseLength, RewardSound = reward_values
                    RewardPumpActive = True
                    RewardPumpEndTime = MasterTime + PulseLength
                    Interface.raise_output(RewardPin)
                    if RewardSound:
                        Beeps[RewardSound].change_gain(stimulus['BaselineGain'])
                    print('Reward!')

        # Visualization # NOTE THAT THIS SLOWS THINGS DOWN BY ABOUT 150 ms (why does it only affect sound???)
        # if (MasterTime % 100) == 0:
        #     visualization.move_mouse_position(TrackPosition)

            
