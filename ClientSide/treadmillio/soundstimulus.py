import time
from subprocess import Popen, DEVNULL

import glob
import os
import warnings
import socket
import signal
from functools import partial
import pickle

from multiprocessing import Process, Pipe, Value, Queue
import pickle

import traceback as tb

from .alsainterface import ALSAPlaybackSystem, ALSARecordSystem
from .alsainterface import normalize_output_device, normalize_input_device, look_for_and_add_stimulus_defaults
from .alsainterface import sort_bundled_sounds

import cProfile

import math
import numba

def db2lin(db_gain):
    return 10.0 ** (db_gain * 0.05)

def run_playback_process(device_name, config, file_dir, control_pipe, log_directory, status_queue):
    status_queue.put(1)
    try: 
        playback_system = ALSAPlaybackSystem(device_name, config, file_dir, control_pipe, log_directory)
    except Exception as e:
        status_queue.put(-1)
        status_queue.close()
        raise e

    status_queue.put(2)  # Signal that we made to loop startup
    status_queue.close()
    try:
        # cProfile.runctx('playback_system.play()', globals(), locals(), "results.prof") # useful for debugging
        print('Playback starting')
        playback_system.play()
    except KeyboardInterrupt:
        print('Caught KeyboardInterrupt in ALSA playback process')
        playback_system.running = False # I don't think this does anything
    except Exception as e:
        raise e

def run_record_process(device_name, config, log_directory, status_queue):
    status_queue.put(1)
    try:
        record_system = ALSARecordSystem(device_name, config, log_directory)
    except Exception as e:
        status_queue.put(-1)
        status_queue.close()
        raise e

    status_queue.put(2) # Signal that we made to loop startup
    status_queue.close()
    try:
        print('Record starting')
        record_system.record()
    except KeyboardInterrupt:
        print('Caught KeyboardInterrupt in ALSA record process')
    except Exception as e:
        raise e


class SoundStimulusController():
    def __init__(self, sound_config, track_length=None, track_topology='Ring', log_directory=None, verbose=0):

        self.valid = False
        # TODO: Handle pipes for multiple audio devices
        # TODO: Error check the YAML file before this to make sure
        #       that sound stimuli specify devices that are in the device list
        #       otherwise, the process will be exit without the main program
        #       realizing it.

        self._playback_processes = []
        self._record_processes = []


        # Start the ALSA playback and record processes.
        #  - ALSA playback will also load all the sound files!


        if 'DeviceList' in sound_config:
            _startup_queue = Queue()
            for dev_name, dev in sound_config['DeviceList'].items():
                if dev['Type'] == 'Output':
                    _playback_read_pipe, self.alsa_playback_pipe = Pipe()  # we'll write to p_master from _this_ process and the ALSA process will read from _playback_read_pipe
                    new_process = Process(target=run_playback_process, args=(dev_name, sound_config, 
                                                sound_config['AudioFileDirectory'], _playback_read_pipe, log_directory, _startup_queue))
                    self._playback_processes.append(new_process)
                    new_process.daemon = True
                    new_process.start()     # Launch the sound process

                    status = _startup_queue.get()
                    while(status < 2):
                        if (status < 0): # error in launching the playback process!
                            _startup_queue.close()
                            new_process.join()
                            raise(RuntimeError("An error occured in starting the ALSA playback process/object."))
                        status = _startup_queue.get()

                elif dev['Type'] == 'Input':
                    new_process = Process(target=run_record_process, args=(dev_name, dev, log_directory, _startup_queue))
                    self._record_processes.append(new_process)
                    new_process.daemon = True
                    new_process.start() # Launch the sound process

                    status = _startup_queue.get()
                    while(status < 2):
                        if (status < 0): # error in launching the playback process!
                            print('Error!')
                            _startup_queue.close()
                            new_process.join()
                            raise(RuntimeError("An error occured in starting the ALSA record process/object."))
                        status = _startup_queue.get()

        # Get stimuli parameters
        StimuliList = look_for_and_add_stimulus_defaults(sound_config)

        # Stimuli placeholders
        self.BackgroundSounds = {}
        self.Beeps = {}
        self.LocalizedStimuli = {}
        self.BundledSounds = {}
        self._Stimuli = {} # suggest private to avoid conflict with above

        # Add stimuli
        for stimulus_name, stimulus in StimuliList.items():
            if verbose > 1:
                print('Adding stimulus {}...'.format(stimulus_name))
            self.add_stimulus(stimulus_name, stimulus, track_length, track_topology, verbose)

        # Add viewer
        if sound_config.get('Viewer', False):
            from .viewer import launch_viewer
            viewer_dict = {name: s.gain for name, s in self._Stimuli.items()}
            viewer_conn, p_viewer = launch_viewer('SoundStimulus', stimuli=viewer_dict)
            for _, sound in self._Stimuli.items():
                sound.connect_viewer(viewer_conn)

        self.valid = True # we won't be valid unless we made it here.

    def add_stimulus(self, stimulus_name, stimulus, track_length, track_topology, verbose=0):
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
            new_stimulus = LocalizedSound(track_length, track_topology, stimulus_name, stimulus, self.alsa_playback_pipe, verbose)
            self.LocalizedStimuli[stimulus_name] = new_stimulus
        elif stimulus['Type'] == 'MultilapBackground':
            if not track_length:
                raise(ValueError('SoundStimulus: Illegal to define a "MultilapBackgroundSound" sound without defining the Maze->Length.'))
            if track_topology != 'Ring':
                raise(Warning('SoundStimulus: Unlikely that MultilapBackground" will work as expected with non-Ring topology.'))
            # visualization.add_zone_position(??? , ???, fillcolor=stimulus['Color'])
            new_stimulus = MultilapBackgroundSound(track_length, stimulus_name, stimulus, self.alsa_playback_pipe, verbose)
            self.LocalizedStimuli[stimulus_name] = new_stimulus
        elif stimulus['Type'] == 'Bundle':
            new_stimulus = BundledSound(stimulus_name, stimulus, self.alsa_playback_pipe, verbose)
            self.BundledSounds[stimulus_name] = new_stimulus
            new_stimulus.change_gain(new_stimulus.baseline_gain)
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

    def update_localized(self, pos, unwrapped_pos):
        update_dict = {}
        for _, sound in self.LocalizedStimuli.items():
            pos_gain =  sound.pos_update_gain(pos, unwrapped_pos)
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
        tb.print_tb(exc_traceback)

        print('SoundStimulController waiting for ALSA processes to join. TODO: Handle other than KeyboardInterrupt!')
        # TODO: Do we need to differentiate different signals? If it's not KeyboardInterrupt, we need to tell it to stop:
        #self.alsa_playback_pipe.send_bytes(pickle.dumps({'StopMessage': True}))
        while self._playback_processes:
            p = self._playback_processes.pop()
            p.join()
        while self._record_processes:
            p = self._record_processes.pop()
            while p.is_alive(): # trust that it's trying to end
                pass
            p.join()

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
            print('Offgain -90')

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



# @jit
def pos_gain_linear_db_ring(x, center, track_length, cutoff, off_gain, max_gain, slope):
    d = abs(center-x) # distance to center #TODO: make sure this can never exceed track length
    relpos = min(d, track_length - d) # account for wrapping around track
    if (relpos > cutoff):
        return off_gain
    else:
        new_gain = max_gain - relpos*slope
        return new_gain

def pos_gain_linear_db_straight(x, center, track_length, cutoff, off_gain, max_gain, slope):
    d = abs(center-x) # distance to center #TODO: make sure this can never exceed track length
    if (d > cutoff):
        return off_gain
    else:
        new_gain = max_gain - d*slope
        return new_gain

# @jit
def pos_gain_natural_ring(x, center, track_length, cutoff, off_gain, max_gain, speaker_distance):
    d = abs(center-x) # distance to center #TODO: make sure this can never exceed track length
    relpos = min(d, track_length - d) # account for wrapping around track # TODO - NEED TO AMMEND FOR LINEAR_TRACK_UPDATE
    if (relpos > cutoff):
        return off_gain
    else:
        new_gain = max_gain - 10*math.log10(relpos**2 + speaker_distance**2) + 20*math.log10(speaker_distance)
        return new_gain

def pos_gain_natural_straight(x, center, track_length, cutoff, off_gain, max_gain, speaker_distance):
    d = abs(center-x) # distance to center #TODO: make sure this can never exceed track length
    if (d > cutoff):
        return off_gain
    else:
        new_gain = max_gain - 10*math.log10(d**2 + speaker_distance**2) + 20*math.log10(speaker_distance)
        return new_gain



class LocalizedSound(SoundStimulus):
    def __init__(self, track_length, track_topology, stimulus_name, stimulus_params, alsa_playback_pipe, verbose):
        SoundStimulus.__init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose)

        # TODO check that these are all set. I need to know my name in order to give
        #  a meaningful warning, though.
        self.center = stimulus_params['CenterPosition']
        self.width = stimulus_params['Modulation']['Width']
        self.half = self.width/2
        self.trackLength = track_length
        self.maxGain = self.baseline_gain
        self.minGain = stimulus_params['Modulation']['CutoffGain']

        if (stimulus_params['Modulation']['Type'] == 'Linear'):
            if track_topology == 'Ring':
                self.pos_gain_function = lambda x : pos_gain_linear_db_ring(x, self.center, 
                                        self.trackLength, self.half, self.off_gain, self.maxGain, 
                                        (self.maxGain - self.minGain)/self.half)
            elif track_topology == 'Line':
                self.pos_gain_function = lambda x : pos_gain_linear_db_straight(x, self.center, 
                                        self.trackLength, self.half, self.off_gain, self.maxGain, 
                                        (self.maxGain - self.minGain)/self.half)
            else:
                raise(ValueError('LocalizedSound: Unsupported track topology {}. "Ring" or "Line" currently supported.'.format(track_topology)))

        elif (stimulus_params['Modulation']['Type'] == 'Natural'):
            if track_topology == 'Ring':
                self.pos_gain_function = lambda x : pos_gain_natural_ring(x, self.center, 
                                        self.trackLength, self.half, self.off_gain, self.maxGain,
                                        stimulus_params['Modulation']['SpeakerDistance'])
            if track_topology == 'Line':
                self.pos_gain_function = lambda x : pos_gain_natural_straight(x, self.center, 
                                        self.trackLength, self.half, self.off_gain, self.maxGain,
                                        stimulus_params['Modulation']['SpeakerDistance'])
            else:
                raise(ValueError('LocalizedSound: Unsupported track topology {}. "Ring" or "Line" currently supported.'.format(track_topology)))

        else:
            raise(ValueError("Unknown modulation function in soundstimulus {}".format(stimulus_params['Modulation']['Type'])))

        if 'MultilapActiveZone' in stimulus_params['Modulation']:
            b = stimulus_params['Modulation']['MultilapActiveZone']
            if len(b) != 2:
                raise(ValueError('SoundStimulus configuration error: MultilapActiveZone should be length 2. Read in {}'.format(b)))
            if (b[0] < 0.0):
                raise(ValueError('MultilapActiveZone must start at or after unwrapped position 0! (Read in {})'.format(b)))
            if (b[1] <= b[0]):
                raise(ValueError('MultilapActiveZone end must come after start! (Read in {})'.format(b)))
            self.multilap_bounds = b
            self.multilap_state = 'waiting'
        else:
            self.multilap_bounds = None

    def pos_update_gain(self, pos, unwrapped_pos):
        new_gain = self.pos_gain_function(pos)

        if self.multilap_bounds:
            if (unwrapped_pos <= self.multilap_bounds[0]) and (self.multilap_state =='waiting'):
                new_gain = self.off_gain
            elif (unwrapped_pos >= self.multilap_bounds[1]) or (self.multilap_state == 'past'): # outside of multilap active zone
                if self.multilap_state == 'inside':
                    self.multilap_state = 'past'
                new_gain = self.off_gain
            else: # inside of multilap active zone OR before and already entered AND did not already go past
                if self.multilap_state == 'waiting':
                    self.multilap_state = 'inside'
                # new_gain = new_gain calculated

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

class MultilapBackgroundSound(SoundStimulus):
    def __init__(self, track_length, stimulus_name, stimulus_params, alsa_playback_pipe, verbose):
        SoundStimulus.__init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose)

        # TODO check that these are all set. I need to know my name in order to give
        #  a meaningful warning, though.
        b = stimulus_params['MultilapActiveZone']
        if len(b) != 2:
            raise(ValueError('SoundStimulus configuration error: MultilapActiveZone should be length 2. Read in {}'.format(b)))
        if (b[0] < 0):
            raise(ValueError('MultilapActiveZone must start at or after unwrapped position 0! (Read in {})'.format(b)))
        if (b[1] <= b[0]):
            raise(ValueError('MultilapActiveZone end must come after start! (Read in {})'.format(b)))
        self.multilap_bounds = b
        self.multilap_state = 'waiting'


    def pos_update_gain(self, pos, unwrapped_pos):
        if (unwrapped_pos <= self.multilap_bounds[0]) and (self.multilap_state =='waiting'):
            new_gain = self.off_gain
        elif (unwrapped_pos >= self.multilap_bounds[1]) or (self.multilap_state == 'past'): # outside of multilap active zone
            if self.multilap_state == 'inside':
                self.multilap_state = 'past'
            new_gain = self.off_gain
        else: # inside of multilap active zone OR before and already entered AND did not already go past
            if self.multilap_state == 'waiting':
                self.multilap_state = 'inside'
            new_gain = self.baseline_gain

        return new_gain
        #SoundStimulus.change_gain(self, new_gain)

    @classmethod
    def valid(cls, name, config):
        base_valid, error = super(MultilapBackgroundSound, cls).valid(name, config)
        if not base_valid:
            return False, error
        if not ('MultilapActiveZone' in config):
            return False, ValueError('Config file processing error: {} is missing "MultilapActiveZone" parameter.'.format(name))

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


class BundledSound(SoundStimulus):
    
    def __init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose):
        SoundStimulus.__init__(self, stimulus_name, stimulus_params, alsa_playback_pipe, verbose)
        #self._file_root = stimulus_params.get('Directory', './')
        #print(os.path.join(self._file_root, stimulus_params['Filename']))
        #print('unsorted: ', glob.glob(os.path.join(self._file_root, stimulus_params['Filename'])))
        #self.filelist = sort_bundled_sounds(glob.glob(os.path.join(self._file_root, stimulus_params['Filename'])))
        #self.num_sounds = len(self.filelist)
        self.num_sounds = stimulus_params.get('Length', math.inf)
        self.index = 0
        #print('filelist: ', self.filelist)
        #self.current_file = self.filelist[self.current_index]
        self.subname = self._get_subname(self.index)
        self.bounds = {} # behavior for handling out of bounds indices
        self.bounds['Low'] = stimulus_params.get('BoundsLow', 'Error')
        self.bounds['High'] = stimulus_params.get('BoundsHigh', 'Error')
        if any([b not in ['Error', 'Soft', 'Wrap', 'Off'] for _, b in self.bounds.items()]):
            raise ValueError('Unknown bounds handling \'{}\'.'.format(self.bounds))

    def _get_subname(self, index):
        if (index >= 0) and (index < self.num_sounds):
            return '-'.join([self.name, str(index)])
        else:
            return None
        
    def change_gain(self, gain):
        if gain != self.gain:
            self.alsa_playback_pipe.send_bytes(pickle.dumps({self.subname: db2lin(gain)}))
            self.gain = gain

        if self._viewer_conn:
            update_dict = {self.name: gain, 'priority': 1}
            self._viewer_conn.send_bytes(pickle.dumps(update_dict))

    def change_gain_raw(self, gain):
        if gain != self.gain:
            self.alsa_playback_pipe.send_bytes(pickle.dumps({self.subname: gain}))
            self.gain = gain

        if self._viewer_conn:
            update_dict = {self.name: gain, 'priority': 1}
            self._viewer_conn.send_bytes(pickle.dumps(update_dict))

    def choose_sound(self, index):
        # Determine index if out of bounds
        if not isinstance(index, int):
            raise TypeError('Index must be an instance of int.')
        elif index < 0:
            index = self._handle_bounds(index, side='Low')
        elif index >= self.num_sounds:
            index = self._handle_bounds(index, side='High')

        # Turn off old sound
        gain = self.gain # cache current gain first
        self.change_gain(self.off_gain)

        # Update index
        self.index = index
        self.subname = self._get_subname(index)

        # Turn on new sound to current gain
        self.change_gain(gain)

    def _handle_bounds(self, index, side='Low'):
        behavior = self.bounds[side]
        if behavior == 'Soft':
            return min(max(index, 0), self.num_sounds - 1) # keep at boundary
        elif behavior == 'Wrap':
            return index % self.num_sounds # works for both positive and negative indices
        elif behavior == 'Off':
            return index # if subname outside boundary, then no sound plays
        else:
            raise ValueError('Index of {} is outside bounds of filelist.'.format(index))

    @classmethod
    def valid(cls, name, config):
        return super(BundledSound, cls).valid(name, config)


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
        elif stim['Type'] == 'MultilapBackground':
            valid, error = MultilapBackgroundSound.valid(stim_name, stim)
        elif stim['Type'] == 'Localized':
            valid, error = LocalizedSound.valid(stim_name, stim)
        elif stim['Type'] == 'Beep':
            valid, error = BeepSound.valid(stim_name, stim)
        elif stim['Type'] == 'Bundle':
            valid, error = BundledSound.valid(stim_name, stim)
        else:
            raise(ValueError('Sound stimulus {} has an unknown stimulus type {}.'.format(stim_name, stim)))
        if not valid:
            raise(error)

        if not stim['Device'] in OutputDevices:
            raise(ValueError("Sound stimulus {} names a device ({}) that is not specified as the channel of a device.".format(stim_name, stim['Device'])))
