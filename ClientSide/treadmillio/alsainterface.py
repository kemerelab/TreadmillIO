#!/usr/bin/env python3

# Simple test script that plays (some) wav files

from __future__ import print_function

import sys
import scipy.io.wavfile
import alsaaudio
import numpy as np
from itertools import cycle
import os
import argparse
import yaml
from multiprocessing import Process, Pipe
import time
import pickle
import soundfile
import warnings

#from profilehooks import profile

# Default parameters
DEFAULT_OUTPUT_DEVICE = {'Type': 'Output',
                         'HWDevice': '', # e.g., 'CARD=SoundCard,DEV=0'
                         'NChannels': 2,
                         'DType': 'int16',
                         'BufferSize': 16, 
                         'ChannelLabels': {'Default1': 0, 'Default2': 1}}

DEFAULT_INPUT_DEVICE = {'Type': 'Input',
                        'HWDevice': '',
                        'NChannels': 2,
                        'SamplingRate': 96000,
                        'DType': 'int16',
                        'BufferSize': 1024, 
                        'FilenameHeader': '',
                        'Record': True}


ILLEGAL_STIMULUS_NAMES = ['StopMessage']

class Stimulus():
    def __init__(self, filename, data_buffer, channel, buffer_len, gain_db):
        self.fs, self.stimulus_buffer = scipy.io.wavfile.read(filename)
        # if self.stimulus_buffer.dtype != dtype:
        #     raise(ValueError('Specified dtype for {} is {} but file is actually {}'.format(
        #         filename, dtype, self.stimulus_buffer.dtype)))

        if (self.stimulus_buffer.ndim > 1):
            raise(ValueError('Stimulus {} is not monaural'.format(filename)))

        #self.data = np.zeros((buffer_len,2), dtype=dtype, order='C')
        self.data = data_buffer # pre-initialized matrix (tensor actually) for easy summing

        self.curpos = 0
        self.buffer_len = buffer_len
        self.stimulus_len = len(self.stimulus_buffer)
        self.channel = channel
        self._gain = np.power(10, gain_db/20)
    
    def get_nextbuf(self):
        remainder = self.curpos + self.buffer_len - self.stimulus_len
        if remainder > 0:
            first = self.stimulus_len - self.curpos
            self.data[:first,self.channel] = self.stimulus_buffer[self.curpos:(self.curpos+first)]
            self.data[first:,self.channel] = self.stimulus_buffer[:remainder]
            self.curpos = remainder
        else:
            self.data[:,self.channel] = self.stimulus_buffer[self.curpos:(self.curpos+self.buffer_len)]
            self.curpos += self.buffer_len

        self.data[:] = self.data[:] * self._gain # make sure not to copy!
        # we don't need to return anything because the caller has a view
        # to the memory that self.data is looking at

    @property
    def gain(self):
        return self._gain
    
    @gain.setter
    def gain(self, gain):
        self._gain = gain

class ALSAPlaybackSystem():
    def __init__(self, dev_name, config, file_root, control_pipe):
        self.running = False

        self.control_pipe = control_pipe

        buffer_size = config['DeviceList'][dev_name].get('BufferSize', DEFAULT_OUTPUT_DEVICE['BufferSize'])
        dtype = config['DeviceList'][dev_name].get('DType', DEFAULT_OUTPUT_DEVICE['DType'])
        device = config['DeviceList'][dev_name].get('HWDevice', DEFAULT_OUTPUT_DEVICE['HWDevice'])
        channel_labels = config['DeviceList'][dev_name].get('ChannelLabels', DEFAULT_OUTPUT_DEVICE['ChannelLabels'])
        num_channels = config['DeviceList'][dev_name].get('NChannels', DEFAULT_OUTPUT_DEVICE['NChannels'])


        # Set up stimuli with default values
        StimuliList = config['StimuliList']
        if 'Defaults' in config:
            print('SoundStimulus: setting defaults.')
            for stimulus_name, stimulus in StimuliList.items(): 
                print(' - ',stimulus_name)
                for key, config_item in config['Defaults'].items():
                    if key not in stimulus:
                        stimulus[key] = config_item
                    elif isinstance(config_item, dict):
                        for subkey, sub_config_item in config_item.items():
                            if subkey not in stimulus[key]:
                                stimulus[key][subkey] = sub_config_item

        # Begin by loading sound files
        self.stimuli = {}
        if len(StimuliList) < 1:
            raise(ValueError('Must specify at least one stimulus!'))

        self.data_buf = np.zeros((buffer_size,2,len(StimuliList))) # data buffer for all data
        k = 0
        for stimulus_name, stimulus in StimuliList.items():
            if stimulus_name in ILLEGAL_STIMULUS_NAMES:
                raise(ValueError('{} is an illegal name for a stimulus.'.format(stimulus_name)))

            print('Adding stimulus {}...'.format(stimulus_name))
            if stimulus.get('Device', 'Default1') in channel_labels:
                channel = channel_labels[stimulus.get('Device', 'Default1')]
                gain = stimulus.get('BaselineGain', 0)
                filename = os.path.join(file_root, stimulus['Filename'])
                self.stimuli[stimulus_name] = Stimulus(filename, self.data_buf[:,:,k], channel, buffer_size, gain)
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


        # Open alsa device
        self.adevice = alsaaudio.PCM(device=device)
        self.adevice.setchannels(num_channels) # We'll always present stereo audio
        self.adevice.setrate(self.fs)
        if dtype == 'int16':
            self.adevice.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        else:
            raise(ValueError("dtypes other than 'int16' not currently supported."))
        self.adevice.setperiodsize(buffer_size)

        print('\nALSA playback configuration ' + '-'*10 + '\n')
        self.adevice.dumpinfo()
        print('\n\n')

        self.out_buf = np.zeros((buffer_size,2), dtype=dtype, order='C')
        ######

    def __del__(self):
        self.adevice.close()

    def set_gain(self, stimulus, gain):
        self.stimuli[stimulus].gain = gain

    def play(self):
        print(time.time())
        self.running = True
        while self.running:
            for _, stim in self.stimuli.items():
                stim.get_nextbuf()
            self.out_buf[:] = self.data_buf.sum(axis=2).astype(dtype=self.out_buf.dtype, order='C')
            res, xruns = self.adevice.write(self.out_buf)
            if xruns != 0:
                print('Xrun! {}'.format(xruns))
                print(time.time())

            while self.control_pipe.poll(): # is this safe? too many messages will certainly cause xruns!
                msg = self.control_pipe.recv_bytes()    # Read from the output pipe and do nothing
                commands = pickle.loads(msg)
                # if 'StopMessage' in commands:
                #     print('Got StopMessage in ALSA process.')
                #     break;
                try:
                    for key, gain in commands.items():
                        if key in self.stimuli:
                            self.stimuli[key].gain = gain
                except:
                    print('Exception: ', commands)


        if self.running == False:
            print('SIGINT flag changed.')

class ALSARecordSystem():
    def __init__(self, dev_name, config, log_directory=None):
        self.running = False

        if not log_directory:
            warnings.warn("Recording microphone input to cwd because log file wasn't specified.")
            log_directory = os.getcwd()

        buffer_size = config.get('BufferSize', DEFAULT_INPUT_DEVICE['BufferSize'])
        dtype = config.get('DType', DEFAULT_INPUT_DEVICE['DType'])
        device = config.get('HWDevice', DEFAULT_INPUT_DEVICE['HWDevice'])
        self.fs = config.get('SamplingRate', DEFAULT_INPUT_DEVICE['SamplingRate'])
        self.channels = config.get('NChannels', DEFAULT_INPUT_DEVICE['NChannels'])

        # Open alsa device
        self.adevice = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL, device=device)

        self.adevice.setchannels(self.channels) # We'll always record stereo audio TODO: support many channels
        self.adevice.setrate(self.fs)
        if dtype == 'int16':
            self.adevice.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        else:
            raise(ValueError("dtypes other than 'int16' not currently supported."))

        self.adevice.setperiodsize(buffer_size)

        self.in_buf = np.zeros((buffer_size*4, self.channels), dtype='int16', order='C')

        self.adevice.enable_timestamps()

        self.logfilename = os.path.join(log_directory, 'microphone.wav.log')
        self.soundfilename = os.path.join(log_directory, 'microphone.wav')

        print('Recording microphone input in: {}.\n'.format(self.soundfilename))
        print('\nALSA record configuration ' + '-'*10 + '\n')
        self.adevice.dumpinfo()
        print('\n\n')

        ######

    def __del__(self):
        self.adevice.close()

    def record(self):
        print(time.time())
        with open(self.logfilename, 'w') as logfile, \
            soundfile.SoundFile(self.soundfilename, 'w', self.fs, self.channels, 'PCM_16') as sf:
            print('Timestamps for soundfile frames. Each record is [nsamps, time], where time is CLOCK_MONOTONIC.\n', file=logfile)
            self.running = True
            while self.running:
                nsamp = self.adevice.read_into(self.in_buf)
                t = self.adevice.gettimestamp()
                sf.write(self.in_buf[:nsamp,:])
                print('{}, {}\n'.format(nsamp, t), file=logfile)

            if self.running == False:
                print('SIGINT flag changed.')



