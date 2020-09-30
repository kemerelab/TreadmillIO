#!/usr/bin/env python3

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
Profiling = True


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
parser.add_argument('--output-dir', default=None,
                    help='Directory to write output file (defaults to cwd)')


args = parser.parse_args()
print(args)

if args.param_file == 'defaults.yaml':
    warnings.warn('Using default configuration file. That is almost certainly not what you want to do!')

# YAML parameters: task settings
with open(args.param_file, 'r') as f:
    Config = yaml.safe_load(f)

# ------------------- Validate config file-------------------------------------------------------------
from treadmillio.soundstimulus import validate_sound_config

if 'AuditoryStimuli' in Config:
    validate_sound_config(Config['AuditoryStimuli'])

# ------------------- Setup logging. ------------------------------------------------------------------
DoLogCommands = True
if 'LogCommands' in Config['Preferences']:
    DoLogCommands = Config['Preferences']['LogCommands']

if DoLogCommands:
    auto_log_directory = Config['Preferences'].get('AutoLogDirectory', True) if 'Preferences' in Config else True

    log_directory = Config['Preferences'].get('LogDirectory', None) if 'Preferences' in Config else None
    if log_directory is not None and args.output_dir is not None:
        warnings.warn('The configuration file specifies {} for logging, '
                'but command line has {}. Using command line!\n'.format(log_directory, args.output_dir))
        log_directory = args.output_dir
    elif args.output_dir is not None:
        log_directory = args.output_dir
    elif auto_log_directory:
        now = datetime.datetime.now()
        log_directory = '{}{}'.format('ExperimentLog', now.strftime("%Y-%m-%d_%H%M"))
    else:
        raise(ValueError('You did not specify a directory for experiment logs, and AutoLogDirectory is False.'))

    if not os.path.isabs(log_directory):
        log_directory = os.path.join(os.getcwd(), log_directory)

    orig_log_directory = log_directory
    k=1
    while os.path.exists(log_directory):
        k = k + 1
        log_directory = orig_log_directory + '_' + str(k)

    if log_directory != orig_log_directory:
        warnings.warn('Specified experiment logs directory {} exists, using {}'.format(orig_log_directory, log_directory))

    print('Creating log directory: {}\n'.format(log_directory))
    os.makedirs(log_directory)

else:
    print('#'*80, '\n')
    print('Warning!!! Not logging!!!!')
    print('#'*80, '\n')


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
    if 'WheelDiameter' in Config['Maze']:
        d = Config['Maze']['WheelDiameter'] #cm diameter of the physical wheel; 150cm
    if 'EncoderGain' in Config['Maze']:
        encoder_gain = Config['Maze']['EncoderGain']


#----------------------- Sound stimuli --------------

from treadmillio.soundstimulus import SoundStimulusController

with ExitStack() as stack:
    if 'AuditoryStimuli' in Config and EnableSound:
        SoundController = stack.enter_context(SoundStimulusController(Config['AuditoryStimuli'], virtual_track_length, log_directory))
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

    if DoLogCommands:
        # -------------------------- Set up all the different log files -------------------------------------
        # Log git diffs for provenance

        import git # gitpython
        repo = git.Repo(search_parent_directories=True)

        GitCommit = repo.head.object.hexsha
        GitChangedFiles = [fn.a_path for fn in repo.index.diff(None)]
        GitPatch = [fn.diff for fn in repo.index.diff(None, create_patch=True)]

        with open(os.path.join(log_directory, 'ExperimentCodeDiffs.txt'), 'w') as git_file:
            print(f'   Git Commit: {GitCommit}',file=git_file)
            if GitChangedFiles:
                print(f'   ChangedFiles: {GitChangedFiles}',file=git_file)
                print(f'Patch:\n{GitPatch}',file=git_file)

        # Log config file used
        with open(os.path.join(log_directory, 'ParsedConfig.yaml'), 'w') as yaml_file:
            yaml.dump(Config, yaml_file, indent=4)
            
        # Create data log file and write header
        log_file = stack.enter_context(open(os.path.join(log_directory, 'DataLog.csv'), 'w', newline=''))
        print(f'Experiment Data File.\n   Version {NamedVersion}',file=log_file)
        log_writer = csv.writer(log_file) # logging is actually CSV format


        if StateMachine and DoLogCommands:
            # Create state machine log file and write header
            state_machine_log = stack.enter_context(open(os.path.join(log_directory, 'StatemachineLog.csv'), 'w', newline=''))
            print(f'State Machine Log File.\n   Version {NamedVersion}',file=state_machine_log)
            state_log_writer = csv.writer(state_machine_log)

        if Profiling:
            execution_log = stack.enter_context(open(os.path.join(log_directory, 'execution.csv'), 'w', newline=''))
            execution_writer = csv.writer(execution_log)


    # ------------------- Webcam Video Recording. ------------------------------------------------------------------
    if 'Cameras' in Config:
        from treadmillio.uvccam.uvccam import RunCameraInterface
        if DoLogCommands:
            for cameraname, camera in Config['Cameras'].items():
                camera['LogDirectory'] = log_directory
        else:
            for cameraname, camera in Config['Cameras'].items():
                if camera['RecordVideo']:
                    print('Over-riding camera configuration to not record video or timestamps!!!')
                camera['RecordVideo'] = False

        for cameraname, camera in Config['Cameras'].items():
            shared_termination_flag = RunCameraInterface(camera) # this starts a bunch of processes


    # TODO: Figure out how to handle errors below. The shared termination flag should work, but it doesn't
    
    # ----------------- Initialization
    ##### Actually connect to IO device. We wait until here so that data doesn't get lost/confused in serial buffer

    Interface.connect()

    FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()
    initialUnwrappedencoder = UnwrappedEncoder

    if SoundController:
        SoundController.start_capture() # TODO: This doesn't currently do anything

    if StateMachine:
        StateMachine.start(MasterTime)

    while(True):
        ## every 2 ms happens:
        FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()
        last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
                                    # since read_data() is blocking, this is a farther bound (i.e., ts AFTER) data

        if DoLogCommands:
            log_writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts]) # Log data from serial interface

        if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
            print(f'Heartbeat {MasterTime} - 0x{GPIO:012b}. Pos - {pos}')

        # -------------------- Updates -------------------- 
        Interface.update_pulses() # lower any outstanding GPIO pulses

        if SoundController:
            SoundController.update_beeps(MasterTime) # stop any outstanding beeps

        if StateMachine:
            if DoLogCommands:
                StateMachine.update_statemachine(state_log_writer.writerow) # update the state machine
            else:
                StateMachine.update_statemachine(None) # update the state machine

        unwrapped_pos = (UnwrappedEncoder - initialUnwrappedencoder) / encoder_gain *d *np.pi 
        pos = unwrapped_pos % virtual_track_length

        if SoundController:
            SoundController.update_localized(pos) # update VR-position-dependent sounds

        if RewardZones:
            RewardZones.update_reward_zones(MasterTime, pos, GPIO) # update any VR-position rewards

        if Profiling and DoLogCommands:
            exec_time = time.monotonic() - last_ts
            execution_writer.writerow([exec_time])








# %%
