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


import threading
import socketserver

class ThreadedUDPRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        global MasterTime
        data = self.request[0].strip()
        socket = self.request[1]
        socket.sendto("MasterTime: {}".format(MasterTime).encode(), self.client_address)
        cur_thread = threading.current_thread()
        response = bytes("{}: {}".format(cur_thread.name, data), 'ascii')
        print("{}: {} wrote:".format(cur_thread.name, self.client_address[0]))
        print(data)

class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    pass

def client(ip, port, message):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((ip, port))
        sock.sendall(bytes(message, 'ascii'))
        response = str(sock.recv(1024), 'ascii')
        print("Received: {}".format(response))

HOST, PORT = "localhost", 9999

from SerialInterface import SerialInterface


with ThreadedUDPServer((HOST, PORT), ThreadedUDPRequestHandler) as server:
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
    server_thread.daemon = True
    server_thread.start()
    print("Server loop running in thread:", server_thread.name)


    Interface = SerialInterface(SerialPort=args.serial_port)
    ## initiate encoder value ##
    FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()
    initialUnwrappedencoder = UnwrappedEncoder 
    print("initial unwrapped encoder value : ", UnwrappedEncoder)

    with open(log_filename, 'w', newline='') as log_file:
        writer = csv.writer(log_file)

        Interface.configure_pin(1, 'OUTPUT', 'AUX')
        Interface.configure_pin(2, 'OUTPUT', 'AUX')
        Interface.configure_pin(3, 'OUTPUT', 'AUX')
        Interface.configure_pin(4, 'OUTPUT', 'AUX')
        Interface.write_pin(1, 1, 'AUX')
        Interface.write_pin(2, 1, 'AUX')
        Interface.write_pin(3, 1, 'AUX')
        Interface.write_pin(4, 1, 'AUX')

        Interface.configure_pin(5, 'OUTPUT', 'DIO')
        Interface.configure_pin(6, 'OUTPUT', 'DIO')
        Interface.configure_pin(7, 'OUTPUT', 'DIO')
        Interface.configure_pin(8, 'OUTPUT', 'DIO')


        while(True):
            ## every 2 ms happens:
            last_ts = time.monotonic()   # to match with miniscope timestamps (which is written in msec, here is sec)
            FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO = Interface.read_data()

            writer.writerow([MasterTime, GPIO, Encoder, UnwrappedEncoder, last_ts])

            if (MasterTime % Config['Preferences']['HeartBeat']) == 0:
                print('Heartbeat {} - {} - 0x{:016b}'.format(MasterTime, UnwrappedEncoder, GPIO))


            
