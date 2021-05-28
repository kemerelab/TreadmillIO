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
import zmq

#from profilehooks import profile

ILLEGAL_STIMULUS_NAMES = ['ConfigDevice','LoadStimuli','Run','Stop']

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
    def __init__(self):
        self.errors = []
        self.running = False
        self.adevice = None
        self.stimuli = None

    def configure_device(self, config):
        device = config.get('HWDevice', '')
        self.buffer_size = config.get('BufferSize', 1024)
        dtype = config.get('DType', 'int16')
        self.fs = config.get('SamplingRate', 96000)
        self.num_channels = config.get('NChannels', 2)
        dev_name = config.get('DeviceName', "Bob")

        log_directory = config.get('LogDirectory', os.getcwd())
        self.logfilename = os.path.join(log_directory, '{}.wav.log'.format(dev_name))
        self.soundfilename = os.path.join(log_directory, '{}.wav'.format(dev_name))
        self.xrun_filename = os.path.join(log_directory, 'alsa_playbacks_xruns.txt')
        #self.num_channels = config['DeviceList'][dev_name]['NChannels']

        # Clean up if we're re-configuring
        if self.adevice:
            self.adevice.close()
            del(self.adevice)

        # Open alsa device
        self.adevice = alsaaudio.PCM(device=device)
        self.adevice.setchannels(self.num_channels) # We'll always present stereo audio
        self.adevice.setrate(self.fs)
        if dtype == 'int16':
            self.adevice.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        # elif dtype == 'int32':
        #     self.adevice.setformat(alsaaudio.PCM_FORMAT_S32_LE)
        else:
            self.errors.append("dtypes other than 'int16' not currently supported.")
            return False
        self.adevice.setperiodsize(self.buffer_size)

        print('\nALSA playback configuration ' + '-'*10 + '\n')
        self.adevice.dumpinfo()
        print('\n\n')

        self.out_buf = np.zeros((self.buffer_size, self.num_channels), dtype=dtype, order='C')

        return True
        ######

    def load_stimuli(self, stimuli_list):
        if not self.adevice:
            self.errors.append("Can't load files without initializing device.")
            return False

        # Begin by loading sound files
        self.num_stimuli = len(stimuli_list)
        if self.num_stimuli < 1:
            self.errors.append("Must specify at least one stimulus.")
            return False

        self.stimuli = {}

        self.data_buf = np.zeros((self.buffer_size, self.num_channels, self.num_stimuli)) # data buffer for all data
        k = 0
        for stimulus_name, stimulus in stimuli_list.items():
            print('Adding stimulus {}...'.format(stimulus_name))
            channel = stimulus.get('Channel', 0)
            gain = stimulus.get('OffGain', 0.0) #-90.0
            try:
                self.stimuli[stimulus_name] = Stimulus(stimulus['Filename'], self.data_buf[:,:,k], channel, self.buffer_size, gain, window=self.buffer_size) # default to Hanning window!
            except:
                self.errors.append("Error loading {}.".format(stimulus['Filename']))
                return False


        # Check to make sure all the sampling rates came out the same
        self.fs = set([stim.fs for _, stim in self.stimuli.items()])
        if len(self.fs) > 1:
            for _, stim in self.stimuli.items():
                print('{}: fs = {}'.format(stim.filename, stim.fs))
            #raise(ValueError('Not all stimuli had the same sampling rate.'))
            self.errors.append('Not all stimuli had the same sampling rate.')
            return False
        else:
            self.fs = self.fs.pop()

        return True


    def __del__(self):
        if self.adevice:
            self.adevice.close()

    def set_gain(self, stimulus, gain):
        self.stimuli[stimulus].gain = gain

    def play(self, socket):
        print(time.time())
        if not self.adevice:
            self.errors.append("No device configured.")
            return False

        if not self.stimuli:
            self.errors.append("No stimuli specified.")
            return False

        with open(self.xrun_filename, 'w') as xrun_logfile:
            self.running = True
            socket.send(b"Running") # Send back a message that we started successfully

            poller = zmq.Poller()
            poller.register(socket, zmq.POLLIN)

            tstart = 0
            tend = 0
            i = 0
            while self.running:
                for _, stim in self.stimuli.items():
                    stim.get_nextbuf()
                self.out_buf[:] = self.data_buf.sum(axis=2).astype(dtype=self.out_buf.dtype, order='C')
                res, xruns = self.adevice.write(self.out_buf) # Blocking!!!
                if xruns != 0:
                    print('xrun in playback [{}] at {}'.format(xruns, time.monotonic()))
                    print('xrun in playback [{}] at {}'.format(xruns, time.monotonic()), file=xrun_logfile)

                tstart = time.time()
                msg_list = poller.poll(timeout=0)
                tend = time.time()
                i = i + 1
                if i == 100:
                    print(tend-tstart)
                    i = 0

                if msg_list:
                    for sock, num in msg_list:
                        msg = socket.recv()
                        commands = pickle.loads(msg)
                        if 'Stop' in commands:
                            print('Got StopMessage in ALSA process.')
                            self.running = False
                            break;
                        else:
                            try:
                                for key, gain in commands.items():
                                    if key in self.stimuli:
                                        self.stimuli[key].gain = gain
                                    elif key is not None: # pass if key is None
                                        raise ValueError('Unknown stimulus {}.'.format(key))
                            except:
                                self.running = False
                                print('Exception: ', commands)

        return True
        
def main():
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 7910

    context = zmq.Context()
    socket = context.socket(zmq.PAIR)
    socket.connect("tcp://localhost:%s" % port)

    exiting = False

    playback = ALSAPlaybackSystem()

    while not exiting:
        msg = socket.recv()
        commands = pickle.loads(msg)
        print(commands)
        if "Exit" in commands:
            exiting = True
        elif "ConfigDevice" in commands:
            ret = playback.configure_device(commands)
            if ret:
                socket.send(b"ConfigSuccess")
            else:
                socket.send(b"ConfigFailure")
        elif "LoadStimuli" in commands:
            commands.pop("LoadStimuli")
            print(commands)
            ret = playback.load_stimuli(commands)
            if ret:
                socket.send(b"LoadSuccess")
            else:
                socket.send(b"LoadFailure")
        elif "Run" in commands:
            ret = playback.play(socket)
            socket.send(b"Stopped")

    socket.send(b"Exiting")

if __name__ == '__main__':
    main()