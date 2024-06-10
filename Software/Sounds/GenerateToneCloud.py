#!/usr/bin/env python
# coding: utf-8

# # Generate Tone Cloud Audio for Behavior Task

# ## Initial setup
import wave, struct, math
import numpy as np
from scipy import signal
import os, json
import matplotlib.pyplot as plt

output_dir = os.getcwd()
print(output_dir)


# ## Tone Cloud (See notes in Jupyter Notebooks in this directory)

def sample_octaves(f_low, f_high, size=1):
    return np.exp(np.log(f_low) + (np.log(f_high) - np.log(f_low))*np.random.random(size=size))


def tone_cloud(fs, T, A, 
               num_tones=5,
               f_low=2000,
               f_high=40000,
               t_chord=0.050,
               t_gate=0.005):
    # Determine number of samples
    N = int(fs*T)
    num_chords = int(T/t_chord)
    n_chord = int(t_chord*fs)
    t = np.arange(n_chord)/fs
    
    # Create sine gate at borders
    gate = np.ones(len(t))
    if t_gate > 0.0:
        f_gate = 1.0/(2*t_gate) # t_gate = 0.5*period
        idx = int(t_gate*fs) # last/first index of ramping
        gate[:idx] = (1.0 + np.cos(2*math.pi*f_gate*t[:idx] + math.pi))/2
        gate[-idx:] = gate[:idx][::-1]

    # Create chords (can run continuously if needed)
    y = np.zeros(N)
    for i in range(num_chords):
        f_c = sample_octaves(f_low, f_high, size=num_tones)
        y_c = np.sin(2*math.pi*f_c[:, np.newaxis]*t[np.newaxis, :])
        y[i*n_chord:(i+1)*n_chord] = gate*np.sum(y_c, axis=0)

    # Normalize
    return y*(A/np.max(y))


sampling_rates = [48000.0, 96000.0, 192000.0]

for fs in sampling_rates:
    sound_dir = os.path.join(output_dir, "{}kHz".format(int(fs/1000)))
    if not os.path.isdir(sound_dir):
        print('Creating output directory {}'.format(sound_dir))
        
        os.makedirs(sound_dir)

    filename = 'tone_cloud_long.wav'

    # Audio settings
    num_channels = 1 # 1 = mono, 2 = stereo (stereo doesn't work)
    T = 600.0 # duration (s)
    A_max = 2**15-1 # max amplitude (short)
    A = 0.5*A_max # sample amplitude
    num_tones = 5 # number of tones in chord
    f_low = 2000 # low frequency (Hz)
    f_high = 40000 # high frequency (Hz)
    t_chord = 0.050 # chord duration (s)
    t_gate = 0.005 # gate duration (s)

    with wave.open(os.path.join(sound_dir, filename),'wb') as wf:
        # File settings
        wf.setnchannels(num_channels)
        wf.setsampwidth(2) # 2 bytes = short
        wf.setframerate(fs)

        # Create sound
        y = tone_cloud(fs=fs, 
                       T=T, 
                       A=A,
                       num_tones=num_tones,
                       f_low=f_low,
                       f_high=f_high,
                       t_chord=t_chord,
                       t_gate=t_gate)
        y = y.astype(np.int16)

        # Write frames to file object
        for i in range(len(y)):
            s = struct.pack('<h', y[i]) # pack as short
            for j in range(num_channels):
                wf.writeframesraw(s)
                
        # Save sound parameters
    with open(os.path.join(sound_dir,filename.split('.')[0] + '.json'), 'w') as f:
        d = {'num_channels': num_channels,
             'fs': fs, 
             'T': T,
             'A': A,
             'num_tones': num_tones,
             'f_low': f_low,
             'f_high': f_high,
             't_chord': t_chord,
             't_gate': t_gate}
        f.write(json.dumps(d, indent=4))

