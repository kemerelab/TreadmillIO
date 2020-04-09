import argparse
import yaml
import os
import time
import signal
from contextlib import ExitStack
import sys
sys.path.append("..")
from treadmillio.soundstimulus import SoundStimulusController

# Command-line arguments
parser = argparse.ArgumentParser(description='Test sound capture and playback.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyACM0',
                   help='TTY device for USB-serial interface (e.g., /dev/ttyUSB0 or COM10)')
parser.add_argument('-p','--param-file', default='defaults.yaml',  
                    help='YAML file containing task parameters')
parser.add_argument('-R','--random-seed', default=None,  
                    help='Random seed. If specified, this also overrides the YAML configuration file.')
parser.add_argument('-o', '--output-dir', default='./',
                    help='Directory to write output file (defaults to cwd)')
parser.add_argument('-v', '--verbose', type=int, choices=[0, 1, 2, 3], default=0,
                    help='Verbosity level.')
args = parser.parse_args()
if not os.path.isdir(args.output_dir):
    os.mkdir(args.output_dir)
if not args.output_dir.endswith('/'):
    args.output_dir += '/'
print(args)

# YAML parameters: task settings
with open(args.param_file, 'r') as f:
    Config = yaml.safe_load(f)

#signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

with ExitStack() as stack:

    SoundController = stack.enter_context(SoundStimulusController(Config['AuditoryStimuli'], verbose=args.verbose))

    # Begin sound capture
    SoundController.start_capture(args.output_dir)

    # Switch pink noise and tone cloud on two speakers
    for i in range(5):
        print('Switching...')
        SoundController.update_stimulus('InterpatchSound', 'Speaker1', 'On')
        SoundController.update_stimulus('InPatchSound', 'Speaker1', 'Off')
        SoundController.update_stimulus('InterpatchSound', 'Speaker2', 'Off')
        SoundController.update_stimulus('InPatchSound', 'Speaker2', 'On')
        time.sleep(5)

        print('Switching...')
        SoundController.update_stimulus('InterpatchSound', 'Speaker1', 'Off')
        SoundController.update_stimulus('InPatchSound', 'Speaker1', 'On')
        SoundController.update_stimulus('InterpatchSound', 'Speaker2', 'On')
        SoundController.update_stimulus('InPatchSound', 'Speaker2', 'Off')
        time.sleep(5)

print('Finished.')


