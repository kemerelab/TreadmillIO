#!/usr/bin/env python3

# Simple test script that plays (some) wav files

import sys
import scipy.io.wavfile
import alsaaudio
import numpy as np
from itertools import cycle
import os
import glob
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
                         'BufferSize': 256,
                         'FS': 48000, 
                         'ChannelLabels': {'Default1': 0, 'Default2': 1}}


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
    def __init__(self, stimulus_data, data_buffer, channel, buffer_len, window=None):
        self.stimulus_buffer = stimulus_data

        self.data = data_buffer # pre-initialized matrix (tensor actually) for easy summing

        self.n_channels = data_buffer.shape[1]

        self.curpos = 0
        self.buffer_len = buffer_len
        self.stimulus_len = len(self.stimulus_buffer)
        self.channel = channel
        self._gain = 0 # np.power(10, gain_db/20)
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
    def __init__(self, device_config, stimuli_config, control_pipe):
        self.running = False
        self.adevice = None

        warnings.warn("XRuns will be logged in cwd.")
        log_directory = os.getcwd()

        self.xrun_filename = os.path.join(log_directory, 'alsa_playback_xruns.txt')

        self.control_pipe = control_pipe

        # config['DeviceList'][dev_name] = normalize_output_device(config['DeviceList'][dev_name])

        buffer_size = device_config['BufferSize']
        dtype = device_config['DType']
        device = device_config['HWDevice']
        # channel_labels = config['DeviceList'][dev_name]['ChannelLabels']
        num_channels = device_config['NChannels']
        fs = device_config['FS']

        # Process stimuli
        if not stimuli_config:
            raise ValueError("Sound playback requires at least one stimulus.")

        self.num_stimuli = len(stimuli_config)
        self.data_buf = np.zeros((buffer_size,num_channels,self.num_stimuli)) # data buffer for all data

        k = 0
        self.stimuli = {}
        for stimulus_name, data in stimuli_config.items():
            if stimulus_name in ILLEGAL_STIMULUS_NAMES:
                raise(ValueError('{} is an illegal name for a stimulus.'.format(stimulus_name)))

            print('Adding stimulus {}...'.format(stimulus_name))

            channel = data['Channel']
            # gain = data.get('OffGain', -90.0) # I think there's no reason to make this configurable
            self.stimuli[stimulus_name] = Stimulus(data['StimData'], self.data_buf[:,:,k], 
                                                   channel, buffer_size, window=buffer_size) # default to Hanning window!
            k = k + 1

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
        self.adevice.setrate(fs)
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

    def play(self, stop_event):
        print(time.time())
        with open(self.xrun_filename, 'w') as xrun_logfile:
            while True:
                for _, stim in self.stimuli.items():
                    stim.get_nextbuf()
                self.out_buf[:] = self.data_buf.sum(axis=2).astype(dtype=self.out_buf.dtype, order='C')
                res = self.adevice.write(self.out_buf)
                # if xruns != 0:
                #     print('xrun in playback [{}] at {}'.format(xruns, time.monotonic()))
                #     print('xrun in playback [{}] at {}'.format(xruns, time.monotonic()), file=xrun_logfile)

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
                            elif key is not None: # pass if key is None
                                raise ValueError('Unknown stimulus {}.'.format(key))
                    except:
                        print('Exception: ', commands)

                if stop_event.is_set():
                    print('Breaking beacuse of a stop event.')
                    break


def normalize_output_device(config):
    for key, value in DEFAULT_OUTPUT_DEVICE.items():
        config[key] = config.get(key, value)

    return config

# def look_for_and_add_stimulus_defaults(config):
#     if 'Defaults' in config:
#         print('SoundStimulus: setting defaults.')
#         for stimulus_name, stimulus in config['StimuliList'].items(): 
#             print(' - ',stimulus_name)
#             for key, config_item in config['Defaults'].items():
#                 if key not in stimulus:
#                     stimulus[key] = config_item
#                 elif isinstance(config_item, dict):
#                     for subkey, sub_config_item in config_item.items():
#                         if subkey not in stimulus[key]:
#                             stimulus[key][subkey] = sub_config_item

    # return config['StimuliList']
