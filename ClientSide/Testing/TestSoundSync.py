import argparse
import yaml
import os
import time, datetime
import signal
import csv
from contextlib import ExitStack
import sys
sys.path.append("..")
from treadmillio.soundstimulus import SoundStimulusController
from treadmillio.serialinterface import SerialInterface
from treadmillio.taskstatemachine import TaskStateMachine

# Command-line arguments: computer settings
parser = argparse.ArgumentParser(description='Run simple linear track experiment.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyACM0',
                   help='TTY device for USB-serial interface (e.g., /dev/ttyUSB0 or COM10)')
parser.add_argument('-C','--param-file', default='defaults.yaml',  
                    help='YAML file containing task parameters')
parser.add_argument('-o', '--output-dir', default='./',
                    help='Directory to write output file (defaults to cwd)')
parser.add_argument('-v', '--verbose', type=int, choices=[0, 1, 2, 3], default=0,
                    help='Verbosity level.')
parser.add_argument('-d', '--duration', type=float, default=0.0,
                    help='Duration to run test (0.0 = no limit).')
args = parser.parse_args()
if not os.path.isdir(args.output_dir):
    os.mkdir(args.output_dir)
if not args.output_dir.endswith('/'):
    args.output_dir += '/'
print(args)

# Create log file
now = datetime.datetime.now()
log_filename = '{}{}.txt'.format('Log', now.strftime("%Y-%m-%d %H%M"))
log_filename = os.path.join(args.output_dir, log_filename)

# YAML parameters: task settings
with open(args.param_file, 'r') as f:
    Config = yaml.safe_load(f)

with ExitStack() as stack:
    # Add sound controller
    SoundController = stack.enter_context(SoundStimulusController(Config['AuditoryStimuli'], verbose=args.verbose))
    SoundController.start_capture(args.output_dir)

    # Add serial interface
    Interface = stack.enter_context(SerialInterface(SerialPort=args.serial_port, config=Config['GPIO']))
    Interface.connect()
    FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()

    # Start state machine
    StateMachine = stack.enter_context(TaskStateMachine(Config['StateMachine'], Interface, SoundController))
    StateMachine.start(MasterTime)

    # Log file
    log_file = stack.enter_context(open(log_filename, 'w', newline=''))
    writer = csv.writer(log_file)

    # Check duration
    if args.duration <= 0.0:
        EndTime = math.inf
    else:
        EndTime = MasterTime + args.duration*1000

    while(MasterTime < EndTime):
        ## every 2 ms happens:
        FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()
        last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
                                    # since read_data() is blocking, this is a farther bound (i.e., ts AFTER) data

        writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts, time.time()]) # Log data from serial interface

        if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
            print(f'Heartbeat {MasterTime} - 0x{GPIO:012b}')

        Interface.update_pulses() # lower any outstanding GPIO pulses

        StateMachine.update_statemachine(writer.writerow) # update the state machine

      
