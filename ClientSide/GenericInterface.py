#!/usr/bin/env python

#%%
# This implements a logger and generic interface for the Teensy IO board.

import time
import datetime
import os
import argparse
import yaml
import csv
import numpy as np


global MasterTime

### Maybe should add argcomplete for this program?

# Command-line arguments: computer settings
# Command-line arguments: computer settings
parser = argparse.ArgumentParser(description='Log data and expose a generic interface for Teensy IO board.')
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


from SerialInterface import SerialInterface

Interface = SerialInterface(SerialPort=args.serial_port)

if 'GPIO' in Config:
    for gpio_label, gpio_config in Config['GPIO'].items():
        Interface.add_gpio(gpio_label, gpio_config)

Interface.connect()


## initiate encoder value ##
FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()
initialUnwrappedencoder = UnwrappedEncoder 
print("initial unwrapped encoder value : ", UnwrappedEncoder)

with open(log_filename, 'w', newline='') as log_file:
    writer = csv.writer(log_file)


    while(True):
        ## every 2 ms happens:
        last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
        FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()

        writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts])

        if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
            print('Heartbeat {} - {} - 0x{:016b}'.format(MasterTime, UnwrappedEncoder, GPIO))


        
