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
import shutil
import argparse
import yaml
import csv
import zmq
import numpy as np
import warnings

from contextlib import ExitStack


NamedVersion = '1.2'
Profiling = False


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
parser.add_argument('--no-check-space', default=None,
                    help='Exits if less than 10 GB of space is available.')


args = parser.parse_args()
print(args)

if args.param_file == 'defaults.yaml':
    warnings.warn('Using default configuration file. That is almost certainly not what you want to do!')

# YAML parameters: task settings
with open(args.param_file, 'r') as f:
    Config = yaml.safe_load(f)

# ------------------- Validate config file-------------------------------------------------------------
if 'AuditoryStimuli' in Config:
    from treadmillio.soundstimulus import validate_sound_config
    validate_sound_config(Config['AuditoryStimuli'])

# ------------------- Setup logging. ------------------------------------------------------------------
DoLogCommands = Config['Preferences'].get('LogCommands', True)

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
        log_root = Config['Preferences'].get('LogDirectoryRoot', '') if 'Preferences' in Config else ''
        log_directory = os.path.join(log_root, '{}{}'.format('ExperimentLog', now.strftime("%Y-%m-%d_%H%M")))
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

    # Check for available space!
    if not args.no_check_space:
        disk_total, disk_used, disk_free = shutil.disk_usage(log_directory)
        if disk_free < 10*1024.0**3: # if less than 10 GB is available, exit
            print("\n!!!!    Only {} MB available, exiting. Use the '--no-check-space' "
             "command line option to override.    !!!!".format(disk_free/(1024.0**2)))
            os.removedirs(log_directory)
            exit(0)

else:
    print('#'*80, '\n')
    print('Warning!!! Not logging!!!!')
    print('#'*80, '\n')
    log_directory = None

EnableSound = Config['Preferences'].get('EnableSound', False)

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


with ExitStack() as stack:
    # --------------  Initialize Serial IO - Won't actually do anything until we call connect()! --------------------------
    from treadmillio.serialinterface import SerialInterface

    gpio_config = Config.get('GPIO', None)
    if not gpio_config:
        warnings.warn("No GPIOs specified in config file. All IOs will be inputs.", RuntimeWarning)

    maze_config = Config.get('Maze', None)

    if 'Preferences' in Config:
        zmq_streaming = Config['Preferences'].get('DataStreamingPort', None)
    
    Interface = stack.enter_context(SerialInterface(SerialPort=args.serial_port, gpio_config=gpio_config, 
                                                    maze_config=maze_config, zmq_streaming=zmq_streaming))

    #----------------------- Sound stimuli --------------
    if 'AuditoryStimuli' in Config and EnableSound:
        from treadmillio.soundstimulus import SoundStimulusController
        SoundController = stack.enter_context(SoundStimulusController(Config['AuditoryStimuli'], Interface.virtual_track_length, 
                                              Interface.maze_topology, log_directory))
    else:
        SoundController = None
        if 'AuditoryStimuli' in Config:
            warnings.warn("Config file specified AuditoryStimuli, but EnableSound is False.", RuntimeWarning)


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

        if RewardZones and DoLogCommands:
            # Create state machine log file and write header
            reward_zone_log = stack.enter_context(open(os.path.join(log_directory, 'RewardzoneLog.csv'), 'w', newline='', buffering=1))
            print(f'Reward Zone Log File.\n   Version {NamedVersion}',file=reward_zone_log)
            reward_zone_writer = csv.writer(reward_zone_log)


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

    # ------------------- Webcam Video Recording. ------------------------------------------------------------------
    if 'GigE-Cameras' in Config:
        from treadmillio.camera.gigecam import RunCameraInterface
        if DoLogCommands:
            for cameraname, camera in Config['GigE-Cameras'].items():
                camera['LogDirectory'] = log_directory
        else:
            for cameraname, camera in Config['GigE-Cameras'].items():
                if camera['RecordVideo']:
                    print('Over-riding camera configuration to not record video or timestamps!!!')
                camera['RecordVideo'] = False

        for cameraname, camera in Config['GigE-Cameras'].items():
            shared_termination_flag = RunCameraInterface(camera) # this starts a bunch of processes


    # TODO: Figure out how to handle errors below. The shared termination flag should work, but it doesn't
    
    # ----------------- Initialization
    ##### Actually connect to IO device. We wait until here so that data doesn't get lost/confused in serial buffer

    Interface.connect()

    FlagChar, StructSize, MasterTime, InitialEncoder, InitialUnwrappedEncoder, InitialGPIO, AuxGPIO = Interface.read_data() # This will initialize encoder

    if SoundController:
        SoundController.start_capture() # TODO: This doesn't currently do anything

    if StateMachine:
        StateMachine.start(MasterTime)

    first_sample = True

    while(True):
        ## every 2 ms happens:
        FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()
        last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
                                    # since read_data() is blocking, this is a farther bound (i.e., ts AFTER) data

        if DoLogCommands:
            if not first_sample:
                log_writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts, Interface.pos, Interface.velocity]) # Log data from serial interface
            else: # for ths first sample, to synchronize to a meaningful clock, we the CLOCK_REALTIME time, in the first row 
                sys_ts = time.time()
                log_writer.writerow([0, InitialGPIO, InitialEncoder, UnwrappedEncoder, sys_ts, 0, 0]) 
                log_writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts, Interface.pos, Interface.velocity])
                first_sample = False

        # -------------------- Updates -------------------- 
        Interface.update_pulses() # lower any outstanding GPIO pulses

        if SoundController:
            SoundController.update_beeps(MasterTime) # stop any outstanding beeps

        if StateMachine:
            if DoLogCommands:
                StateMachine.update_statemachine(state_log_writer.writerow) # update the state machine
            else:
                StateMachine.update_statemachine(None) # update the state machine

        # unwrapped_pos = (UnwrappedEncoder - initialUnwrappedencoder) / encoder_gain *d *np.pi 
        # pos = unwrapped_pos % virtual_track_length

        if "Maze" in Config:
            if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
                print(f'Heartbeat {MasterTime} - 0x{GPIO:012b}. Pos - {Interface.pos}. Lap: {Interface.unwrapped_pos // Interface.virtual_track_length}. Speed: {Interface.velocity}')
                if StateMachine:
                    print(StateMachine.CurrentState.label)

        if SoundController:
            SoundController.update_localized(Interface.pos, Interface.unwrapped_pos) # update VR-position-dependent sounds

        if RewardZones:
            if DoLogCommands:
                RewardZones.update_reward_zones(MasterTime, Interface.pos, GPIO, reward_zone_writer.writerow) # update any VR-position rewards
            else:
                RewardZones.update_reward_zones(MasterTime, Interface.pos, GPIO) # update any VR-position rewards

        if Profiling and DoLogCommands:
            exec_time = time.monotonic() - last_ts
            execution_writer.writerow([exec_time])




# %%
