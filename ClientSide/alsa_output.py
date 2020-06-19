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

#from profilehooks import profile

DEFAULT_OUTPUT_DEVICE = {'Type': 'Output',
                         'Channel': 0}

DEFAULT_BUFFER_SIZE = 16
DEFAULT_DTYPE = 'int16'

class Stimulus():
    def __init__(self, filename, data_buffer, channel, buffer_len, gain):
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
        self.gain = np.power(10, gain/20)
    
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

        self.data[:] = self.data[:] * self.gain # make sure not to copy!
        # we don't need to return anything because the caller has a view
        # to the memory that self.data is looking at


class ALSAPlaybackSystem():
    def __init__(self, config, device):
        file_root = config.get('AudioFileDirectory', None)
        buffer_size = config.get('BufferSize', DEFAULT_BUFFER_SIZE)
        dtype = config.get('DType', DEFAULT_DTYPE)

        DeviceList = config.get('DeviceList', {'Default': DEFAULT_OUTPUT_DEVICE})

        self._devices = {}
        for device_name, dev in DeviceList.items():
            if dev['Type'] == 'Output':
                print('Adding device {}...'.format(device_name))
                self._devices[device_name] = dev['Channel']

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
            print('Adding stimulus {}...'.format(stimulus_name))
            channel = self._devices[stimulus.get('Device', 'Default')]
            gain = stimulus.get('BaselineGain', 0)
            filename = os.path.join(file_root, stimulus['Filename'])
            self.stimuli[stimulus_name] = Stimulus(filename, self.data_buf[:,:,k], channel, buffer_size, gain)
            k = k + 1

        # Check to make sure all the sampling rates came out the same
        self.fs = set([stim.fs for _, stim in self.stimuli.items()])
        if len(self.fs) > 1:
            for _, stim in self.stimuli.items():
                print('{}: fs = {}'.format(stim.filename, stim.fs))
            raise(ValueError('Not all stimuli had the same sampling rate.'))
        else:
            self.fs = self.fs.pop()

        # Open alsa device
        self.adevice = alsaaudio.PCM(device=device)
        self.adevice.setchannels(2) # We'll always present stereo audio
        self.adevice.setrate(self.fs)
        if dtype == 'int16':
            self.adevice.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        else:
            raise(ValueError("dtypes other than 'int16' not currently supported."))
        self.adevice.setperiodsize(buffer_size)

        self.out_buf = np.zeros((buffer_size,2), dtype=dtype, order='C')

    def play(self):
        while True:
            for _, stim in self.stimuli.items():
                stim.get_nextbuf()
            self.out_buf[:] = self.data_buf.sum(axis=2).astype(dtype=self.out_buf.dtype, order='C')
            res, xruns = self.adevice.write(self.out_buf)
            if xruns != 0:
                print('Xrun! {}'.format(xruns))


def run_audio_process(config, device):
    sound_system = ALSAPlaybackSystem(config, device)
    sound_system.play()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run simple linear track experiment.')
    parser.add_argument('-C','--param-file', default='defaults.yaml',  
                        help='YAML file containing task parameters')
    parser.add_argument('-d','--device', default='default',  
                        help='ALSA device for playback')
    args = parser.parse_args()
    print(args)

    # YAML parameters: task settings
    with open(args.param_file, 'r') as f:
        config = yaml.safe_load(f)

    audio_p = Process(target=run_audio_process, args=(config['AuditoryStimuli'], args.device))
    audio_p.daemon = True
    audio_p.start()     # Launch the sound process

    audio_p.join()

