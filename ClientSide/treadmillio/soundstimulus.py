import time
from subprocess import Popen, DEVNULL

import os
import warnings
import socket
import signal
from functools import partial
import pickle
from .viewer import launch_viewer

from multiprocessing import Process, Pipe, Value
import pickle

from .alsainterface import ALSAPlaybackSystem, ALSARecordSystem
from .alsainterface import normalize_output_device, normalize_input_device, look_for_and_add_stimulus_defaults

import cProfile

def db2lin(db_gain):
    return 10.0 ** (db_gain * 0.05)


def run_audio_playback_process(device_name, config, file_dir, control_pipe, log_directory):
    playback_system = ALSAPlaybackSystem(device_name, config, file_dir, control_pipe, log_directory)
    try:
        # cProfile.runctx('playback_system.play()', globals(), locals(), "results.prof") # useful for debugging
        print('Playback starting')
        playback_system.play()
    except KeyboardInterrupt:
        print('Caught KeyboardInterrupt in ALSA playback process')
        playback_system.running = False # I don't think this does anything

def run_audio_record_process(device_name, config, log_directory):
    record_system = ALSARecordSystem(device_name, config, log_directory)
    try:
        print('Record starting')
        record_system.record()
    except KeyboardInterrupt:
        print('Caught KeyboardInterrupt in ALSA record process')


class SoundStimulusController():
    def __init__(self, sound_config, track_length=None, log_directory=None, verbose=0):

        # TODO: Handle pipes for multiple audio devices
        # TODO: Error check the YAML file before this to make sure
        #       that sound stimuli specify devices that are in the device list
        #       otherwise, the process will be exit without the main program
        #       realizing it.

        self._audio_playback_process = None
        self._audio_record_process = None

        if 'DeviceList' in sound_config:
            for dev_name, dev in sound_config['DeviceList'].items():
                if dev['Type'] == 'Output':
                    _playback_read_pipe, self.alsa_playback_pipe = Pipe()  # we'll write to p_master from _this_ process and the ALSA process will read from _playback_read_pipe
                    self._audio_playback_process = Process(target=run_audio_playback_process, args=(dev_name, sound_config, 
                                                sound_config['AudioFileDirectory'], _playback_read_pipe, log_directory))
                    self._audio_playback_process.daemon = True
                    self._audio_playback_process.start()     # Launch the sound process
                elif dev['Type'] == 'Input':
                    self._audio_record_process = Process(target=run_audio_record_process, args=(dev_name, dev, log_directory))
                    self._audio_record_process.daemon = True
                    self._audio_record_process.start()     # Launch the sound process


        # Get stimuli parameters
        StimuliList = look_for_and_add_stimulus_defaults(sound_config)

        # Stimuli placeholders
        self.BackgroundSounds = {}
        self.Beeps = {}
        self.LocalizedStimuli = {}
        self._Stimuli = {} # suggest private to avoid conflict with above

        # Add stimuli
        for stimulus_name, stimulus in StimuliList.items():
            if verbose > 1:
                print('Adding stimulus {}...'.format(stimulus_name))
            self.add_stimulus(stimulus_name, stimulus, track_length, verbose)

    def add_stimulus(self, stimulus_name, stimulus, track_length=None, verbose=0):
        # Add to type-specific mapping
        stimulus['Name'] = stimulus_name
        if stimulus['Type'] == 'Background':
            new_stimulus = SoundStimulus(stimulus_name, stimulus, self.alsa_playback_pipe, verbose)
            self.BackgroundSounds[stimulus_name] = new_stimulus
            new_stimulus.change_gain(new_stimulus.baseline_gain)
            #visualization.add_zone_position(0, VirtualTrackLength, fillcolor=stimulus['Color'], width=0.5, alpha=0.75)
        elif stimulus['Type'] == 'Beep':
            new_stimulus = BeepSound(stimulus_name, stimulus, self.alsa_playback_pipe, verbose)
            self.Beeps[stimulus_name] = new_stimulus
        elif stimulus['Type'] == 'Localized':
            if not track_length:
                raise(ValueError('SoundStimulus: Illegal to define a "Localized" sound without defining the Maze->Length.'))
            # visualization.add_zone_position(stimulus['CenterPosition'] - stimulus['Modulation']['Width']/2, 
            #                     stimulus['CenterPosition'] + stimulus['Modulation']['Width']/2, 
            #                     fillcolor=stimulus['Color'])
            new_stimulus = LocalizedSound(track_length, stimulus_name, stimulus, self.alsa_playback_pipe, verbose)
            self.LocalizedStimuli[stimulus_name] = new_stimulus
        else:
            raise ValueError('Unknown stimulus type \'{}\'.'.format(stimulus['Type']))

        # Add to general mapping
        if stimulus_name in self._Stimuli:
            raise ValueError('Multiple stimuli cannot share the same name.')
        else:
            self._Stimuli[stimulus_name] = new_stimulus

    def get_stimulus(self, stimulus_name):
        # TODO: Is this the best to map same objects?
        if stimulus_name in self._Stimuli:
            return self._Stimuli[stimulus_name]
        else:
            raise KeyError('No sound stimulus with name \'{}\'.'.format(stimulus_name))

    def start_capture(self):
        pass

    def stop_capture(self):
        pass

    def update_beeps(self, time):
        update_dict = {}
        for _, beep in self.Beeps.items():
            new_beep_value = beep.update(time)
            if new_beep_value is not None:
                update_dict[beep.name] = db2lin(new_beep_value)
        if update_dict:
            self.alsa_playback_pipe.send_bytes(pickle.dumps(update_dict)) # update all at once!

    def update_localized(self, pos):
        update_dict = {}
        for _, sound in self.LocalizedStimuli.items():
            pos_gain =  sound.pos_update_gain(pos)
            if pos_gain is not None:
                update_dict[sound.name] =  db2lin(pos_gain)
        if update_dict:
            self.alsa_playback_pipe.send_bytes(pickle.dumps(update_dict)) # update all at once!

    def update_stimulus(self, stimulus, value):
        # TODO: error checking
        gain = None
        if isinstance(value, str):
            if value.lower() in ['on', 'baseline']:
                gain = stimulus.baseline_gain
            elif value.lower() == 'off':
                gain = stimulus.off_gain
        elif isinstance(value, (int, float)):
            gain = value

        if gain is None:
            raise ValueError('Value of {} not understood.'.format(value))
        else:
            return stimulus.change_gain(gain)

    def __del__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        print('SoundStimulController: exiting because of exception <{}>'.format(exc_type.__name__))
        print('SoundStimulController waiting for ALSA processes to join. TODO: Handle other than KeyboardInterrupt!')
        # TODO: Do we need to differentiate different signals? If it's not KeyboardInterrupt, we need to tell it to stop:
        #self.alsa_playback_pipe.send_bytes(pickle.dumps({'StopMessage': True}))
        if self._audio_playback_process:
            self._audio_playback_process.join()
        if self._audio_record_process:
            while self._audio_record_process.is_alive(): # trust that it's trying to end
                pass
            self._audio_record_process.join()

class SoundStimulus():
    def __init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose):
        self.name = stimulus_name
        self.alsa_playback_pipe = alsa_playback_pipe

        # Gain parameters
        if 'BaselineGain' in stimulus_params:
            self.baseline_gain = stimulus_params['BaselineGain']
        else:
            warnings.warn("SoundStimulus using default 'BaselineGain' of 0.0 dB.", RuntimeWarning)
            self.baseline_gain = 0.0
        if 'OffGain' in stimulus_params:
            self.off_gain = stimulus_params['OffGain']
        else:
            self.off_gain = -90.0 

        # Set gain prior to playing sound
        self.gain = self.off_gain # NOTE: Is it easier to have sounds off initially?
        self.alsa_playback_pipe.send_bytes(pickle.dumps({self.name: db2lin(self.gain)}))

        self.device = stimulus_params['Device']
        self.verbose = verbose

        # Pipe for updating viewer
        self._viewer_conn = None

        time.sleep(0.25)

    def connect_viewer(self, pipe):
        self._viewer_conn = pipe

    def change_gain(self, gain):
        if gain != self.gain:
            self.alsa_playback_pipe.send_bytes(pickle.dumps({self.name: db2lin(gain)}))
            self.gain = gain

        if self._viewer_conn:
            update_dict = {self.name: gain, 'priority': 1}
            self._viewer_conn.send_bytes(pickle.dumps(update_dict))

    def change_gain_raw(self, gain):
        if gain != self.gain:
            self.alsa_playback_pipe.send_bytes(pickle.dumps({self.name: gain}))
            self.gain = gain

        if self._viewer_conn:
            update_dict = {self.name: gain, 'priority': 1}
            self._viewer_conn.send_bytes(pickle.dumps(update_dict))

    @classmethod
    def valid(cls, name, config):
        if not ('Device' in config):
            return False, ValueError('Config file processing error: {} is missing "Device" parameter.'.format(name))

        return True, None

class LocalizedSound(SoundStimulus):
    def __init__(self, track_length, stimulus_name, stimulus_params, alsa_playback_pipe, verbose):
        SoundStimulus.__init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose)

        # TODO check that these are all set. I need to know my name in order to give
        #  a meaningful warning, though.
        self.center = stimulus_params['CenterPosition']
        self.width = stimulus_params['Modulation']['Width']
        self.half = self.width/2
        self.trackLength = track_length
        self.maxGain = self.baseline_gain
        self.minGain = stimulus_params['Modulation']['CutoffGain']

    def linear_gain_from_pos(self, pos):
        relpos = (pos - self.center) % self.trackLength
        if (relpos  > self.trackLength / 2):
            relpos = relpos - self.trackLength
        elif (relpos < -self.trackLength / 2):
            relpos = relpos + self.trackLength
        if (abs(relpos) > self.half):
            return self.off_gain
        else:
            return (1 - abs(relpos/self.half)) * (self.maxGain - self.minGain) + self.minGain

    def pos_update_gain(self, pos):
        relpos = (pos - self.center) % self.trackLength
        if (relpos  > self.trackLength / 2):
            relpos = relpos - self.trackLength
        elif (relpos < -self.trackLength / 2):
            relpos = relpos + self.trackLength
        if (abs(relpos) > self.half):
            new_gain = self.off_gain
        else:
            new_gain = (1 - abs(relpos/self.half)) * (self.maxGain - self.minGain) + self.minGain

        return new_gain
        #SoundStimulus.change_gain(self, new_gain)

    @classmethod
    def valid(cls, name, config):
        base_valid, error = super(LocalizedSound, cls).valid(name, config)

        if not base_valid:
            return False, error
        if not ('CenterPosition' in config):
            return False, ValueError('Config file processing error: {} is missing "CenterPosition" parameter.'.format(name))
        if not ('Modulation' in config):
            return False, ValueError('Config file processing error: {} is missing "Modulation" parameters.'.format(name))
        if not ('Width' in config['Modulation']):
            return False, ValueError('Config file processing error: {} is missing "Modulation" parameters.'.format(name))
        if not ('Width' in config['Modulation']):
            return False, ValueError('Config file processing error: {} is missing "Modulation: Width" parameter.'.format(name))
        if not ('CutoffGain' in config['Modulation']):
            return False, ValueError('Config file processing error: {} is missing "Modulation: CutoffGain" parameter.'.format(name))

        return True, None



class BeepSound(SoundStimulus):
    def __init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose):
        SoundStimulus.__init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose)
        if 'Duration' in stimulus_params:
            self.duration = stimulus_params['Duration']
        else:
            raise(ValueError('Config file processing error - a "Duration" must be specified for a "Beep"-type AuditoryStimulus.'))

        self.is_playing = False
        self.time_beep_off = -1

        SoundStimulus.change_gain(self,-90.0) # beep for a very short moment
        
    def play(self, now):
        if self.is_playing:
            warnings.warn("Beep triggered while playing.", RuntimeWarning)
        self.time_beep_off = now + self.duration
        SoundStimulus.change_gain(self,self.baseline_gain)
        self.is_playing = True
    
    def update(self, time):
        if self.is_playing:
            if (time > self.time_beep_off):
                self.is_playing = False
                # SoundStimulus.change_gain(self,self.off_gain)
                return self.off_gain
        return None # if we didn't already return!

    @classmethod
    def valid(cls, name, config):
        base_valid, error = super(BeepSound, cls).valid(name, config)
        if not base_valid:
            return False, error
        if not ('Duration' in config):
            return False, ValueError('Config file processing error: {} is missing "Duration" parameter.'.format(name))
        return True, None


def validate_sound_config(config):
    # What do we want to test:
    #   After we optionally specified defaults, SoundStimuli have all the proper settings
    #   Device defaults set
    #   SoundStimuli have a "Device" that matches DeviceList/Device/ChannelLabels/***

    # First - normalize the Stimuli and Devices
    OutputDevices = []
    for dev_name, dev in config['DeviceList'].items():
        if dev['Type'] == 'Output':
            config['DeviceList'][dev_name] = normalize_output_device(config['DeviceList'][dev_name])
            OutputDevices.extend(config['DeviceList'][dev_name]['ChannelLabels'].keys())
        if dev['Type'] == 'Input':
            config['DeviceList'][dev_name] = normalize_input_device(config['DeviceList'][dev_name])

    config['StimuliList'] = look_for_and_add_stimulus_defaults(config)

    for stim_name, stim in config['StimuliList'].items():
        if stim['Type'] == 'Background':
            valid, error = SoundStimulus.valid(stim_name, stim)
        elif stim['Type'] == 'Localized':
            valid, error = LocalizedSound.valid(stim_name, stim)
        elif stim['Type'] == 'Beep':
            valid, error = BeepSound.valid(stim_name, stim)
        else:
            raise(ValueError('Sound stimulus {} has an unknown stimulus type {}.'.format(stim_name, stim)))
        if not valid:
            raise(error)

        if not stim['Device'] in OutputDevices:
            raise(ValueError("Sound stimulus {} names a device ({}) that is not specified as the channel of a device.".format(stim_name, stim['Device'])))

