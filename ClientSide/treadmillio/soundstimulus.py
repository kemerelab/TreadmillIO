import time
from subprocess import Popen, DEVNULL
import jack # pip install JACK-client
from oscpy.client import OSCClient
import os
import warnings
import socket
import signal

@jack.set_error_function
def error(msg):
    print('JackClientError:', msg)

# Suppress printing of JACK Client info when we start it up later
@jack.set_info_function
def info(msg):
    pass

def minimixer_cmd(speaker):
    return ['/usr/local/bin/jackminimix', 
            '-{}'.format(args.side[0]), '{}:{}'.format(speaker['ClientName'], speaker['PortName']), 
            '-p', '{}'.format(speaker['OSCPort']),
            '-n', 'minimixer-{}'.format(speaker['Name'])]

def jackplay_cmd(speaker, channel, filename):
    return ['/usr/local/bin/sndfile-jackplay', 
            '-l', '0', 
            '-a=minimixer-{}:{}'.format(speaker['Name'], channel), 
            '{}{}'.format(AUDIO_DIR, filename)]

def jackcapture_cmd(device, output_dir):
    return ['/usr/local/bin/jack_capture',
            '--channels', '1',
            '--port', '{}:{}'.format(device['ClientName'], device['PortName']),
            '--timestamp',
            '--filename-prefix', '{}/{}-'.format(output_dir, device['Name'])]

# Default parameters
DEFAULT_OUTPUT_DEVICE = {'Type': 'Output',
                         'ClientName': 'system',
                         'PortName': 'playback_1',
                         'OscPort': 12345,
                         'MinimixerChannel': 'left',
                         'Record': False}

DEFAULT_INPUT_DEVICE = {'Type': 'Input',
                        'ClientName': 'system',
                        'PortName': 'capture_1',
                        'Record': True}

class SoundStimulusController():

    def __init__(self, sound_config, track_length=None, verbose=0):
        #start jack with = ['/usr/bin/jackd', '--realtime', '-P10','-d', 'alsa', '-p128', '-n2', '-r48000']
        #self.p_jack = Popen(jack_cmd, stdout=DEVNULL, stderr=DEVNULL)

        if 'MaximumNumberOfStimuli' in sound_config:
            totalStimuli = sound_config['MaximumNumberOfStimuli']
        else:
            totalStimuli = 10

        if 'AudioFileDirectory' in sound_config:
            file_root = sound_config['AudioFileDirectory']
        else:
            file_root = None

        StimuliList = sound_config['StimuliList']

        if 'Defaults' in sound_config:
            print('SoundStimulus: setting defaults.')
            for stimulus_name, stimulus in StimuliList.items(): 
                print(' - ',stimulus_name)
                for key, config_item in sound_config['Defaults'].items():
                    if key not in stimulus:
                        stimulus[key] = config_item
                    elif isinstance(config_item, dict):
                        for subkey, sub_config_item in config_item.items():
                            if subkey not in stimulus[key]:
                                stimulus[key][subkey] = sub_config_item

        # Add audio I/O devices
        if 'DeviceList' in sound_config:
            DeviceList = sound_config['DeviceList']
        else:
            DeviceList = {'Default': DEFAULT_OUTPUT_DEVICE}

        self.devices = {}
        self.record_devices = []
        for device_name, device in DeviceList.items():
            if verbose > 1:
                print('Adding device {}...'.format(device_name))
            if 'Type' not in device:
                raise ValueError('Device type must be specified for device \'{}\'.'.format(device_name))
            elif device['Type'].lower() == 'output':
                # Add output device
                self.devices[device_name] = SoundOutputDevice(device_name, device, verbose)
                for stimulus_name, stimulus in StimuliList.items():
                    if 'Device' not in stimulus or 'All' in stimulus['Device'] or device_name in stimulus['Device']:
                        self.devices[device_name].add_stimulus(stimulus_name, stimulus, file_root, track_length)
                if device.get('Record', DEFAULT_OUTPUT_DEVICE['Record']):
                    self.record_devices.append(device_name)
            elif device['Type'].lower() == 'input':
                # Add input device
                self.devices[device_name] = SoundInputDevice(device_name, device, verbose)
                if device.get('Record', DEFAULT_INPUT_DEVICE['Record']):
                    self.record_devices.append(device_name)
            else:
                raise ValueError('Unknown device type \'{}\'.'.format(device['Type']))

            time.sleep(0.25)

    def start_capture(self, file_root):
        for device_name in self.record_devices:
            self.devices[device_name].start_capture(file_root)

    def stop_capture(self):
        for device_name in self.record_devices:
            self.devices[device_name].stop_capture()
        
    def update_beeps(self, time):
        for _, device in self.devices.items():
            if device.type == 'output':
                for _, beep in device.Beeps.items():
                    beep.update(time)

    def update_localized(self, pos):
        for _, device in self.devices.items():
            if device.type == 'output':
                for _, sound in device.LocalizedStimuli.items():
                    sound.pos_update_gain(pos)

    def update_stimulus(self, stimulus, device, value):
        # TODO: error checking
        gain = None
        s = self.devices[device].get_stimulus(stimulus)
        if isinstance(value, str):
            if value.lower() in ['on', 'baseline']:
                gain = s.baseline_gain
            elif value.lower() == 'off':
                gain = s.off_gain
        elif isinstance(value, (int, float)):
            gain = value

        if gain is None:
            raise ValueError('Value of {} not understood.'.format(value))
        else:
            return s.change_gain(gain)

    def close_process(self):
        for _, device in self.devices.items():
            device.close()
                
    def __del__(self):
        self.close_process()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        for _, device in self.devices.items():
            if device.type == 'output':
                for _, stimulus in device._Stimuli.items():
                    stimulus.close_processes()
        self.close_process()

class SoundDevice():

    def __init__(self, name, device_config, verbose=0):
        # NOTE: pass parameters as dictionary or **kwargs?
        # Dictionary sets default as constant dict above; 
        # **kwargs sets defaults directly in __init__()
        
        # Device name and type
        self.name = name
        self.verbose = verbose

        # Record process
        self.p_capture = None

    @property
    def client_name(self):
        raise NotImplementedError

    @property
    def port_name(self):
        raise NotImplementedError

    def start_capture(self, file_root):
        cmd = ['/usr/local/bin/jack_capture',
               '--channels', '1',
               '--port', '{}:{}'.format(self.client_name, self.port_name),
               '--timestamp',
               '--filename-prefix', '{}/{}-'.format(file_root, self.name), # will not overwrite file
               '--jack-name', 'jack_capture-{}'.format(self.name),
               '--no-stdin'] 
        if self.verbose > 2:
            self.p_capture = Popen(cmd)
        else:
            self.p_capture = Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)

        return True

    def stop_capture(self, timeout=10.0):
        if self.p_capture:
            msg_name = 'jack_capture-{} on {}:{}'.format(self.name, self.client_name, self.port_name)
            self.p_capture.send_signal(signal.SIGINT)
            try:
                if self.p_capture.wait(timeout) != 0:
                    warnings.warn('Error closing {}.'.format(msg_name))
                elif self.verbose > 2:
                    print('Closed {}.'.format(msg_name))
            except TimeoutError:
                warnings.warn('{} timed out. Killing process...'.format(msg_name))
                self.p_capture.kill()
            self.p_capture = None

    def close(self):
        self.stop_capture()
        self._close()
    
    def _close(self):
        pass
            

class SoundInputDevice(SoundDevice):
    def __init__(self, name, device_config, verbose=0):
        SoundDevice.__init__(self, name, device_config, verbose)

        # Settings
        self.type = 'input'

        # Create JACK client
        try:
            jack_client = jack.Client('PythonJackClient', no_start_server=True)
        except jack.JackError:
            raise(EnvironmentError("Jack server not started"))

        # Check JACK ports
        self._client_name = device_config.get('ClientName', DEFAULT_INPUT_DEVICE['ClientName'])
        self._port_name = device_config.get('PortName', DEFAULT_INPUT_DEVICE['PortName'])
        input_port = '{}:{}'.format(self._client_name, self._port_name)
        if not jack_client.get_ports(input_port, is_output=True):
            raise EnvironmentError('JACK capture port {} not found.'.format(input_port))
        
        # Close client
        jack_client.close()

    @property
    def client_name(self):
        return self._client_name

    @property
    def port_name(self):
        return self._port_name

class SoundOutputDevice(SoundDevice):

    def __init__(self, name, device_config, verbose=0):
        SoundDevice.__init__(self, name, device_config, verbose)

        # Settings
        self.type = 'output'

        # Placeholders
        self.BackgroundSounds = {}
        self.Beeps = {}
        self.LocalizedStimuli = {}
        self._Stimuli = {} # suggest private to avoid conflict with above

        # Create JACK client
        try:
            jack_client = jack.Client('PythonJackClient', no_start_server=True)
        except jack.JackError:
            raise(EnvironmentError("Jack server not started"))
        

        # Check JACK ports
        self._client_name = device_config.get('ClientName', DEFAULT_OUTPUT_DEVICE['ClientName'])
        self._port_name = device_config.get('PortName', DEFAULT_OUTPUT_DEVICE['PortName'])
        output_port = '{}:{}'.format(self.client_name, self.port_name)
        if not jack_client.get_ports(output_port, is_input=True):
            raise EnvironmentError('JACK playback port {} not found.'.format(output_port))

        # Check OSC port (warning or exception?)
        self.osc_port = device_config.get('OscPort', DEFAULT_OUTPUT_DEVICE['OscPort'])
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind((socket.gethostname(), self.osc_port))
            except OSError as e:
                if e.errno == 98:
                    warnings.warn('OscPort {} already in use.'.format(self.osc_port))

        # Get minimixer channel
        self.channel = device_config.get('MinimixerChannel', DEFAULT_OUTPUT_DEVICE['MinimixerChannel']).lower()
        if self.channel not in ['left', 'right']:
            raise ValueError('Minimixer channel must be \'left\' or \'right\' but is \'{}\''.format(self.channel))
            
        # Handle the minimixer already running
        self.minimixer = 'minimixer-{}'.format(self.name)
        if not jack_client.get_ports(self.minimixer, is_input=True): # minimix not started
            # Start minimixer with device parameters
            minimixer_cmd = ['/usr/local/bin/jackminimix', 
                             '-{}'.format(self.channel[0]), '{}:{}'.format(self.client_name, self.port_name), 
                             '-p', '{}'.format(self.osc_port),
                             '-n', self.minimixer]
            if (self.verbose > 1):
                self.p_minimix = Popen(minimixer_cmd)
            else:
                self.p_minimix = Popen(minimixer_cmd, stdout=DEVNULL, stderr=DEVNULL)

            # Check for connection
            for i in range(5):
                if jack_client.get_ports(self.minimixer, is_input=True):
                    break
                time.sleep(1.0)
            if jack_client.get_ports(self.minimixer, is_input=True):
                print('JACK {} started'.format(self.minimixer))
            else:
                raise(EnvironmentError("Could not start minimixer"))
        else:
            print('Connecting to existing minimixer instance.')

        # Close client
        jack_client.close() 

    @property
    def client_name(self):
        return self._client_name

    @property
    def port_name(self):
        return self._port_name

    def add_stimulus(self, stimulus_name, stimulus, file_root, track_length=None):
        # Add to type-specific mapping
        if stimulus['Type'] == 'Background':
            new_stimulus = SoundStimulus(stimulus, file_root, self.osc_port, self.verbose, self.minimixer)
            self.BackgroundSounds[stimulus_name] = new_stimulus
            #visualization.add_zone_position(0, VirtualTrackLength, fillcolor=stimulus['Color'], width=0.5, alpha=0.75)
        elif stimulus['Type'] == 'Beep':
            new_stimulus = BeepSound(stimulus, file_root, self.osc_port, self.verbose, self.minimixer)
            self.Beeps[stimulus_name] = new_stimulus
        elif stimulus['Type'] == 'Localized':
            if not track_length:
                raise(ValueError('SoundStimulus: Illegal to define a "Localized" sound without defining the Maze->Length.'))
            # visualization.add_zone_position(stimulus['CenterPosition'] - stimulus['Modulation']['Width']/2, 
            #                     stimulus['CenterPosition'] + stimulus['Modulation']['Width']/2, 
            #                     fillcolor=stimulus['Color'])
            new_stimulus = LocalizedSound(track_length, stimulus, file_root, self.osc_port, self.verbose, self.minimixer)
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

    def _close(self, timeout=10.0):
        if self.p_minimix:
            self.p_minimix.send_signal(signal.SIGINT)
            try:
                if self.p_minimix.wait(timeout) != 0:
                    warnings.warn('Error closing {}.'.format(self.minimixer))
                elif self.verbose > 2:
                    print('Closed {}.'.format(self.minimixer))
            except TimeoutError:
                warnings.warn('{} timed out. Killing process...'.format(self.minimixer))
                self.p_minimix.kill()
            self.p_minimix = None


class SoundStimulus():
    def __init__(self, stimulus_params, file_root, osc_port, verbose, minimixer=None):
        if 'BaselineGain' in stimulus_params:
            self.baseline_gain = stimulus_params['BaselineGain']
        else:
            warnings.warn("SoundStimulus using default 'BaselineGain' of 0.0 dB.", RuntimeWarning)
            self.baseline_gain = 0.0
        
        if 'OffGain' in stimulus_params:
            self.off_gain = stimulus_params['OffGain']
        else:
            self.off_gain = -90.0 

        self.p_jackplay = None

        jack_client = jack.Client('PythonJackClient', no_start_server=True)

        filename = stimulus_params['Filename']
        self.name = filename
        if file_root is not None:
            filename = os.path.join(file_root, filename)
        if not os.path.isfile(filename):
            raise(ValueError("Sound file {} could not be found.".format(filename)))
        else:
            if verbose > 1:
                print('Loading: {}'.format(filename))

        self.filename = filename
        
        if minimixer is None:
            minmixer = 'minimixer'

        if 'MinimixChannel' in stimulus_params:
            channel = stimulus_params['MinimixChannel'].lower()
            if channel not in ['left', 'right']:
                raise(ValueError("MinimixChannel should be 'left' or 'right'."))
        else:
            channel = 'left'

        if 'MinimixInputPort' in stimulus_params:
            self.inputPort = stimulus_params['MinimixInputPort']
            portName = '{}:in{}_{}'.format(minimixer, self.inputPort, channel)
            if jack_client.get_all_connections(portName):
                raise(ValueError("Specified port {} is already connected".format(portName)))
        else: # Auto assign a new minimxer port to this stimulus
            availablePortNames = [p.name for p in jack_client.get_ports('{}:'.format(minimixer), is_input=True)]
            if availablePortNames is None:
                raise(EnvironmentError("Jack minimix appears not to be running."))

            self.inputPort = None
            inputPort = 1

            portName = '{}:in{}_{}'.format(minimixer, inputPort, channel)            
            while portName in availablePortNames:
                if not jack_client.get_all_connections(portName):
                    self.inputPort = inputPort
                    break;
                else:
                    inputPort = inputPort + 1
                    portName = '{}:in{}_{}'.format(minimixer,inputPort,channel)
            
        if not jack_client.get_ports(portName):
            raise(EnvironmentError("Not enough minimixer ports. Restart with 'MaximumNumberOfStimuli' of at least {}".format(inputPort)))
        else:
            if (verbose > 1):
                print('Input port: {}'.format(self.inputPort))

        jack_client.close()

        # Set gain prior to playing sound
        self.gain = self.off_gain # NOTE: Is it easier to have sounds off initially?
        self.oscC = OSCClient('127.0.0.1', int(osc_port))
        self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), self.gain])

        jackplay_cmd = ['/usr/local/bin/sndfile-jackplay', '-l0', '-a={}:in{}_{}'.format(minimixer,self.inputPort,channel), '{}'.format(filename)]
        if (verbose > 1):
            print(jackplay_cmd)
        
        if verbose > 2:
            self.p_jackplay = Popen(jackplay_cmd)
        else:
            self.p_jackplay = Popen(jackplay_cmd, stdout=DEVNULL, stderr=DEVNULL)

        # Save variables for class methods
        self.minimixer = minimixer
        self.channel = channel
        self.verbose = verbose

        time.sleep(0.25)

    def change_gain(self, gain):
        if gain != self.gain:
            self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), gain])
            self.gain = gain

    def close_processes(self, timeout=10.0):
        if self.p_jackplay:
            msg_name = 'jackplay-{} on {}:in{}_{}'.format(self.name, self.minimixer, self.inputPort, self.channel)
            self.p_jackplay.send_signal(signal.SIGINT)
            try:
                if self.p_jackplay.wait(timeout) != 0:
                    warnings.warn('Error closing {}.'.format(msg_name))
                elif self.verbose > 2:
                    print('Closed {}.'.format(msg_name))
            except TimeoutError:
                warnings.warn('{} timed out. Killing process...'.format(msg_name))
                self.p_jackplay.kill()
            self.p_jackplay = None

    def __del__(self):
        self.close_processes()


class LocalizedSound(SoundStimulus):
    def __init__(self, track_length, stimulus_params, file_root, osc_port, verbose):
        SoundStimulus.__init__(self,stimulus_params, file_root, osc_port, verbose)

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

        SoundStimulus.change_gain(self, new_gain)


class BeepSound(SoundStimulus):
    def __init__(self, stimulus_params, file_root, osc_port, verbose):
        SoundStimulus.__init__(self,stimulus_params, file_root, osc_port, verbose)
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
                SoundStimulus.change_gain(self,self.off_gain)
                self.is_playing = False
