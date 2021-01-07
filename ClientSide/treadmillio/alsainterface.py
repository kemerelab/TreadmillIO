#!/usr/bin/env python3

# Simple test script that plays (some) wav files

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
import signal

#from profilehooks import profile

# Default parameters
DEFAULT_OUTPUT_DEVICE = {'Type': 'Output',
                         'HWDevice': '', # e.g., 'CARD=SoundCard,DEV=0'
                         'NChannels': 2,
                         'NPeriods': 4,
                         'DType': 'int16',
                         'BufferSize': 32, 
                         'ChannelLabels': {'Default1': 0, 'Default2': 1}}

DEFAULT_INPUT_DEVICE = {'Type': 'Input',
                        'HWDevice': '',
                        'NChannels': 2,
                        'SamplingRate': 96000,
                        'DType': 'int16',
                        'BufferSize': 1024, 
                        'FilenameHeader': ''}


ILLEGAL_STIMULUS_NAMES = ['StopMessage']

def tukey_window(N, N_overlap=None):
    # tukey_window(N, N_overlap=None) -> full_window, left_lobe_and_top, right_lobe
    #
    # The Tukey window is a commonly used window for granular synthesis.
    # It's a cosine lobe with a flat top. For the sake of this code, our
    # definition is a bit non-standard. For the equivalent of a Hanning
    # window, the right setting is N_overlap=N. That's because we construct
    # a window of size N+N_overlap.

    if N_overlap == 0:
        # rectangular window!
        return np.ones(N), np.ones(N), None
        
    N2 = N + N_overlap
    n = np.arange(0,N2,1)
    L = (N2+1)
    alpha = N_overlap * 2 / L # want alpha * L / 2 to be an integer
    w = np.ones(N2)
    w[:N_overlap] = 1/2 * (1 - np.cos(2*np.pi*n[:N_overlap]/(alpha * L)))
    w[-N_overlap:] = 1/2 * (1 - np.cos(2*np.pi*(N2-n[-N_overlap:])/(alpha * L)))

    w_prime = np.zeros(N)
    w_prime[:N_overlap] = w[-N_overlap:]

    return w, w[:-N_overlap], w_prime

class Stimulus():
    def __init__(self, filename, data_buffer, channel, buffer_len, gain_db, window=None):
        self.fs, self.stimulus_buffer = scipy.io.wavfile.read(filename)
        # if self.stimulus_buffer.dtype != dtype:
        #     raise(ValueError('Specified dtype for {} is {} but file is actually {}'.format(
        #         filename, dtype, self.stimulus_buffer.dtype)))

        if (self.stimulus_buffer.ndim > 1):
            raise(ValueError('Stimulus {} is not monaural'.format(filename)))

        #self.data = np.zeros((buffer_len,2), dtype=dtype, order='C')
        self.data = data_buffer # pre-initialized matrix (tensor actually) for easy summing

        self.n_channels = data_buffer.shape[1]

        self.curpos = 0
        self.buffer_len = buffer_len
        self.stimulus_len = len(self.stimulus_buffer)
        self.channel = channel
        self._gain = np.power(10, gain_db/20)
        self._current_gain = self._gain # current_gain will allow us to track changes

        self._windowing = window is not None

        if window is not None:
            _, self._new_window, self._old_window = tukey_window(self.buffer_len, window)
            self._new_window = np.transpose(np.tile(self._new_window, [self.n_channels, 1])) #
            self._old_window = np.transpose(np.tile(self._old_window, [self.n_channels, 1]))
            self._old_gain = np.zeros((buffer_len,self.n_channels)) # pre-allocate these
            self._new_gain = np.zeros((buffer_len,self.n_channels)) # pre-allocate these
            self._gain_profile = np.zeros((buffer_len,self.n_channels)) # pre-allocate these
    
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

        if (self._windowing) and (self._gain != self._current_gain):
            self._old_gain[:] = self._old_window[:] * self._current_gain
            self._new_gain[:] = self._new_window[:] * self._gain
            self._gain_profile[:] = self._new_gain + self._old_gain
            self._current_gain = self._gain
            self.data[:] = self.data[:] * self._gain_profile
        else:
            self.data[:] = self.data[:] * self._gain # make sure not to copy!
        # we don't need to return anything because the caller has a view
        # to the memory that self.data is looking at

    @property
    def gain(self):
        return self._gain
    
    @gain.setter
    def gain(self, gain):
        self._gain = gain
        # print('Gain: {}'.format(20*np.log10(gain))) # TODO: Add this as debug info

class ALSAPlaybackSystem():
    def __init__(self, dev_name, config, file_root, control_pipe, log_directory=None):
        self.running = False
        self.adevice = None

        if not log_directory:
            warnings.warn("XRuns will be logged in cwd.")
            log_directory = os.getcwd()

        self.xrun_filename = os.path.join(log_directory, 'alsa_playback_xruns.txt')

        self.control_pipe = control_pipe

        config['DeviceList'][dev_name] = normalize_output_device(config['DeviceList'][dev_name])

        buffer_size = config['DeviceList'][dev_name]['BufferSize']
        dtype = config['DeviceList'][dev_name]['DType']
        device = config['DeviceList'][dev_name]['HWDevice']
        channel_labels = config['DeviceList'][dev_name]['ChannelLabels']
        num_channels = config['DeviceList'][dev_name]['NChannels']

        # Set up stimuli with default values
        StimuliList = look_for_and_add_stimulus_defaults(config)

        # Begin by loading sound files
        self.stimuli = {}
        if len(StimuliList) < 1:
            raise(ValueError('Must specify at least one stimulus!'))

        self.data_buf = np.zeros((buffer_size,num_channels,len(StimuliList))) # data buffer for all data
        k = 0
        for stimulus_name, stimulus in StimuliList.items():
            if stimulus_name in ILLEGAL_STIMULUS_NAMES:
                raise(ValueError('{} is an illegal name for a stimulus.'.format(stimulus_name)))

            print('Adding stimulus {}...'.format(stimulus_name))
            if stimulus.get('Device', 'Default1') in channel_labels:
                channel = channel_labels[stimulus.get('Device', 'Default1')]
                gain = stimulus.get('OffGain', -90.0)
                filename = os.path.join(file_root, stimulus['Filename'])
                self.stimuli[stimulus_name] = Stimulus(filename, self.data_buf[:,:,k], channel, buffer_size, gain, window=buffer_size) # default to Hanning window!
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
        # elif dtype == 'int32':
        #     self.adevice.setformat(alsaaudio.PCM_FORMAT_S32_LE)
        else:
            raise(ValueError("dtypes other than 'int16' not currently supported."))
        self.adevice.setperiodsize(buffer_size)

        print('\nALSA playback configuration ' + '-'*10 + '\n')
        self.adevice.dumpinfo()
        print('\n\n')

        self.out_buf = np.zeros((buffer_size,num_channels), dtype=dtype, order='C')
        ######

    def __del__(self):
        if self.adevice:
            self.adevice.close()

    def set_gain(self, stimulus, gain):
        self.stimuli[stimulus].gain = gain

    def play(self):
        print(time.time())
        with open(self.xrun_filename, 'w') as xrun_logfile:
            self.running = True
            while self.running:
                for _, stim in self.stimuli.items():
                    stim.get_nextbuf()
                self.out_buf[:] = self.data_buf.sum(axis=2).astype(dtype=self.out_buf.dtype, order='C')
                res, xruns = self.adevice.write(self.out_buf)
                if xruns != 0:
                    print('xrun in playback [{}] at {}'.format(xruns, time.monotonic()))
                    print('xrun in playback [{}] at {}'.format(xruns, time.monotonic()), file=xrun_logfile)

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
        self.adevice = None

        if not log_directory:
            warnings.warn("Recording microphone input to cwd because log file wasn't specified.")
            log_directory = os.getcwd()

        self.xrun_filename = os.path.join(log_directory, 'alsa_record_xruns.txt')

        config = normalize_input_device(config)

        self.buffer_size = config['BufferSize']
        dtype = config['DType']
        device = config['HWDevice']
        self.fs = config['SamplingRate']
        self.channels = config['NChannels']

        # Open alsa device
        self.adevice = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL, device=device)

        self.adevice.setchannels(self.channels) # We'll always record stereo audio TODO: support many channels
        self.adevice.setrate(self.fs)
        scale_factor = 4 # system fixed number of buffers
        if dtype == 'int16':
            self.adevice.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            scale_factor = scale_factor*2
        # elif dtype == 'int32':
        #     scale_factor = scale_factor*4
        #     self.adevice.setformat(alsaaudio.PCM_FORMAT_S32_LE)
        else:
            raise(ValueError("dtypes other than 'int16' not currently supported."))

        self.adevice.setperiodsize(self.buffer_size)


        self.in_buf = np.zeros((self.buffer_size*scale_factor, self.channels), dtype=dtype, order='C')

        self.adevice.enable_timestamps()

        self.logfilename = os.path.join(log_directory, '{}.wav.log'.format(dev_name))
        self.soundfilename = os.path.join(log_directory, '{}.wav'.format(dev_name))

        print('Recording microphone input in: {}.\n'.format(self.soundfilename))
        print('\nALSA record configuration ' + '-'*10 + '\n')
        self.adevice.dumpinfo()
        print('\n\n')

        self.soundfile = None
        self.logfile = None
        self.xrun_logfile = None

        ######

    def __del__(self):
        if self.adevice:
            self.adevice.close()


    def record(self):
        print(time.time())
        with open(self.xrun_filename, 'w') as self.xrun_logfile, \
                open(self.logfilename, 'w') as self.logfile, \
                soundfile.SoundFile(self.soundfilename, 'w', self.fs, self.channels, 'PCM_16') as self.soundfile:

            print('Timestamps for soundfile frames. Each record is [nsamps, time], where time is CLOCK_MONOTONIC.\n', file=self.logfile)
            while True:
                nsamp = self.adevice.read_into(self.in_buf)
                t = self.adevice.gettimestamp()
                self.soundfile.write(self.in_buf[:nsamp,:])
                print('{}, {}'.format(nsamp, t), file=self.logfile)
                if nsamp < self.buffer_size:
                    print('ALSA Read buffer underrun.')
                    print('buffer underrun {}'.format(t), file=self.xrun_logfile)


def normalize_output_device(config):
    config['BufferSize'] = config.get('BufferSize', DEFAULT_OUTPUT_DEVICE['BufferSize'])
    config['DType'] = config.get('DType', DEFAULT_OUTPUT_DEVICE['DType'])
    config['Device'] = config.get('HWDevice', DEFAULT_OUTPUT_DEVICE['HWDevice'])
    config['ChannelLabels'] = config.get('ChannelLabels', DEFAULT_OUTPUT_DEVICE['ChannelLabels'])
    config['NChannels'] = config.get('NChannels', DEFAULT_OUTPUT_DEVICE['NChannels'])

    return config


def normalize_input_device(config):
    config['BufferSize'] = config.get('BufferSize', DEFAULT_INPUT_DEVICE['BufferSize'])
    config['DType'] = config.get('DType', DEFAULT_INPUT_DEVICE['DType'])
    config['Device'] = config.get('HWDevice', DEFAULT_INPUT_DEVICE['HWDevice'])
    config['SamplingRate'] = config.get('SamplingRate', DEFAULT_INPUT_DEVICE['SamplingRate'])
    config['NChannels'] = config.get('NChannels', DEFAULT_INPUT_DEVICE['NChannels'])

    return config


def look_for_and_add_stimulus_defaults(config):
    if 'Defaults' in config:
        print('SoundStimulus: setting defaults.')
        for stimulus_name, stimulus in config['StimuliList'].items(): 
            print(' - ',stimulus_name)
            for key, config_item in config['Defaults'].items():
                if key not in stimulus:
                    stimulus[key] = config_item
                elif isinstance(config_item, dict):
                    for subkey, sub_config_item in config_item.items():
                        if subkey not in stimulus[key]:
                            stimulus[key][subkey] = sub_config_item

    return config['StimuliList']
