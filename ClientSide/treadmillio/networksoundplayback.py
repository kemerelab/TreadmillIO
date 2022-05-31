#!/usr/bin/env python3

# Simple test script that plays (some) wav files

import sys
import scipy.io.wavfile
import numpy as np
from itertools import cycle
import os
import glob
from multiprocessing import Process, Pipe
import time
import pickle
import warnings
import zmq

from .alsainterface import look_for_and_add_stimulus_defaults, sort_bundled_sounds

#from profilehooks import profile

# Default parameters
DEFAULT_OUTPUT_DEVICE = {'Type': 'Output',
                         'SoundServer': 'tcp://localhost:7342',
                         'RemoteHWDevice': '', # e.g., 'CARD=SoundCard,DEV=0'
                         'NChannels': 2,
                         'NPeriods': 4,
                         'DType': 'int16',
                         'BufferSize': 32, 
                         'ChannelLabels': {'Default1': 0, 'Default2': 1}}


ILLEGAL_STIMULUS_NAMES = ['StopMessage']

class Stimulus():
    def __init__(self, filename):
        self.fs, self.stimulus_buffer = scipy.io.wavfile.read(filename)
        # if self.stimulus_buffer.dtype != dtype:
        #     raise(ValueError('Specified dtype for {} is {} but file is actually {}'.format(
        #         filename, dtype, self.stimulus_buffer.dtype)))

        if (self.stimulus_buffer.ndim > 1):
            raise(ValueError('Stimulus {} is not monaural'.format(filename)))

    @property
    def gain(self):
        return self._gain
    
    @gain.setter
    def gain(self, gain):
        self._gain = gain
        # print('Gain: {}'.format(20*np.log10(gain))) # TODO: Add this as debug info

class NetworkPlaybackSystem():
    def __init__(self, dev_name, config, file_root, control_pipe, log_directory=None):
        self.running = False
        self.adevice = None

        if not log_directory:
            warnings.warn("XRuns will be logged in cwd.")
            log_directory = os.getcwd()

        self.xrun_filename = os.path.join(log_directory, 'alsa_playback_xruns.txt')

        self.control_pipe = control_pipe

        config['DeviceList'][dev_name] = normalize_network_output_device(config['DeviceList'][dev_name])

        # Next we go through the process of loading all the stimuli into memory

        # Set up stimuli with default values
        StimuliList = look_for_and_add_stimulus_defaults(config)

        # Begin by loading sound files
        self.stimuli = {}
        if len(StimuliList) < 1:
            raise(ValueError('Must specify at least one stimulus!'))

        # Check for number of bundled sounds
        self.num_stimuli = 0
        for stimulus_name, stimulus in StimuliList.items():
            if stimulus['Type'] == 'Bundle':
                root_dir = stimulus.get('Directory', './')
                self.num_stimuli += len(glob.glob(os.path.join(file_root, root_dir, stimulus['Filename'])))
            else:
                self.num_stimuli += 1


        channel_labels = config['DeviceList'][dev_name]['ChannelLabels']
        k = 0
        for stimulus_name, stimulus in StimuliList.items():
            if stimulus_name in ILLEGAL_STIMULUS_NAMES:
                raise(ValueError('{} is an illegal name for a stimulus.'.format(stimulus_name)))

            print('Adding stimulus {}...'.format(stimulus_name))
            if stimulus.get('Device', 'Default1') in channel_labels:
                if stimulus['Type'] == 'Bundle':
                    root_dir = stimulus.get('Directory', './')
                    filelist = sort_bundled_sounds(glob.glob(os.path.join(file_root, root_dir, stimulus['Filename'])))
                    for i, filepath in enumerate(filelist):
                        self.stimuli['-'.join([stimulus_name, str(i)])] = Stimulus(filepath) 
                        k = k + 1
                else:
                    filename = os.path.join(file_root, stimulus['Filename'])
                    self.stimuli[stimulus_name] = Stimulus(filename) 
                    k = k + 1
            else:
                print('When loading stimuli, {} not found in list of SpeakerChannels for device {}'.format(stimulus.get('Device','Default1'), dev_name))

        # Check to make sure all the sampling rates came out the same
        self.fs = set([stim.fs for _, stim in self.stimuli.items()])
        if len(self.fs) > 1:
            for _, stim in self.stimuli.items():
                print('{}: fs = {}'.format(stim.filename, stim.fs))
            raise(ValueError('Not all stimuli had the same sampling rate.'))
        else:
            self.fs = self.fs.pop()

        ####
        # TODO: WHAT HAPPENS IF WE CONTROL C RIGHT DURING THIS????
        # start reading from the pipe to get what ever initialization happens out of the way
        if self.control_pipe.poll():
            msg = self.control_pipe.recv_bytes()    # Read from the output pipe and do nothing
            print('Unexpected message before start: {}'.format(msg))
            print('TODO: Figure out how to shutdown pipes properly\n') # TODO here


        # Open and initialize network device
        buffer_size = config['DeviceList'][dev_name]['BufferSize']
        dtype = config['DeviceList'][dev_name]['DType']
        remote_device = config['DeviceList'][dev_name]['RemoteHWDevice']
        num_channels = config['DeviceList'][dev_name]['NChannels']

        self.sound_server_endpoint = config['DeviceList'][dev_name]['SoundServer']

        self.REQUEST_RETRIES = 3
        self.REQUEST_TIMEOUT = 100
        context = zmq.Context()
        self.sound_server_context = context.socket(zmq.REQ)
        self.sound_server_context.connect(self.sound_server_endpoint)

        retval = self.send_zmq_command({'Command':'Reset'}, b'Reset')
        if not retval:
            raise ValueError("Error in communicating with Sound Server. Is server online and running?")

        retval = self.send_zmq_command({'Command':'Configure', 
                                        'DeviceConfig': config['DeviceList'][dev_name],
                                        'Stimuli': StimuliList}, b'Configured', 2)


        ######

    def send_zmq_command(self, msg, success_reply, wait=0):
        self.sound_server_context.send(pickle.dumps(msg))

        if wait > 0:
            time.sleep(wait)

        return_value = False
        retries_left = self.REQUEST_RETRIES
        while True:
            if (self.sound_server_context.poll(self.REQUEST_TIMEOUT) & zmq.POLLIN) != 0:
                reply = self.sound_server_context.recv()
                print(reply)
                if (reply == success_reply):
                    return_value = True
                    break
                else:
                    continue

            retries_left -= 1
            # Socket is confused. Close and remove it.
            self.sound_server_context.setsockopt(zmq.LINGER, 0)
            self.sound_server_context.close()
            if retries_left == 0:
                print("Server {} seems to be offline, abandoning".format(self.sound_server_endpoint))
                break

            # Create new connection
            context = zmq.Context()
            self.sound_server_context = context.socket(zmq.REQ)
            self.sound_server_context.connect(self.sound_server_endpoint)
            self.sound_server_context.send(pickle.dumps(msg))
            if wait > 0:
                time.sleep(wait)
            

        return return_value


    def __del__(self):
        if self.sound_server_context:
            retval = self.send_zmq_command({'Command':'Exit'}, b'Exiting')
        self.sound_server_context.close()


    def set_gain(self, stimulus_key, gain):
        print('Set gain {}:{}', stimulus_key, gain)
        if self.sound_server_context:
            retval = self.send_zmq_command({'Command':'SetGain', stimulus_key: gain}, b'Gain Set')


    def play(self):
        print(time.time())
        with open(self.xrun_filename, 'w') as xrun_logfile:
            self.running = True
            while self.running:
                while self.control_pipe.poll(): # is this safe?
                    msg = self.control_pipe.recv_bytes()
                    commands = pickle.loads(msg)
                    # if 'StopMessage' in commands:
                    #     print('Got StopMessage in ALSA process.')
                    #     break;
                    try:
                        for key, gain in commands.items():
                            if key in self.stimuli:
                                self.set_gain(key, gain)
                            elif key is not None: # pass if key is None
                                raise ValueError('Unknown stimulus {}.'.format(key))
                    except:
                        print('Exception: ', commands)


        if self.running == False:
            print('SIGINT flag changed.')

def normalize_network_output_device(config):
    config['BufferSize'] = config.get('BufferSize', DEFAULT_OUTPUT_DEVICE['BufferSize'])
    config['DType'] = config.get('DType', DEFAULT_OUTPUT_DEVICE['DType'])
    config['SoundServer'] = config.get('SoundServer', DEFAULT_OUTPUT_DEVICE['SoundServer'])
    config['RemoteHWDevice'] = config.get('RemoteHWDevice', DEFAULT_OUTPUT_DEVICE['RemoteHWDevice'])
    config['ChannelLabels'] = config.get('ChannelLabels', DEFAULT_OUTPUT_DEVICE['ChannelLabels'])
    config['NChannels'] = config.get('NChannels', DEFAULT_OUTPUT_DEVICE['NChannels'])

    return config

