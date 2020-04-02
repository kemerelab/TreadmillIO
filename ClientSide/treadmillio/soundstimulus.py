import time
from subprocess import Popen, DEVNULL
import jack # pip install JACK-client
from oscpy.client import OSCClient
import os
import warnings


@jack.set_error_function
def error(msg):
    print('JackClientError:', msg)

# Suppress printing of JACK Client info when we start it up later
@jack.set_info_function
def info(msg):
    pass

def jackplay_cmd(speaker, channel, filename):
    return ['/usr/local/bin/sndfile-jackplay',
            '-l', '0', # this makes the sound file loop infinitely
            '-a=minimixer-{}:{}'.format(speaker['Name'], channel), 
            '{}'.format(filename)]

def jackcapture_cmd(device):
    return ['/usr/local/bin/jack_capture',
            '--channels', '1',
            '--port', '{}:{}'.format(device['ClientName'], device['PortName']),
            '--timestamp',
            '--filename-prefix', '{}/{}'.format(args.output_dir, device['Name'])]

class SoundStimulusController():
    def __init__(self, sound_config, track_length=None, verbose=0):
        self.p_minimix = None
        self.BackgroundSounds = {}
        self.Beeps = {}
        self.LocalizedStimuli = {}

        #start jack with = ['/usr/bin/jackd', '--realtime', '-P10','-d', 'alsa', '-p128', '-n2', '-r48000']
        #self.p_jack = Popen(jack_cmd, stdout=DEVNULL, stderr=DEVNULL)

        try:
            jack_client = jack.Client('PythonJackClient', no_start_server=True)
        except jack.JackError:
            raise(EnvironmentError("Jack server not started"))

        if 'MaximumNumberOfStimuli' in sound_config:
            totalStimuli = sound_config['MaximumNumberOfStimuli']
        else:
            totalStimuli = 10

        if 'OscPort' in sound_config:
            osc_port = sound_config['OscPort']
        else:
            osc_port = 12345

        # Handle the minimixer already running
        if not jack_client.get_ports('minimixer:', is_input=True): # minimix not started
            minimix_cmd  = ['/usr/local/bin/jackminimix', '-a', '-c', str(totalStimuli), '-p', str(osc_port)]
            if (verbose > 1):
                self.p_minimix = Popen(minimix_cmd)
            else:
                self.p_minimix = Popen(minimix_cmd, stdout=DEVNULL, stderr=DEVNULL)

            for i in range(5):
                if jack_client.get_ports('minimixer:', is_input=True):
                    break
                time.sleep(1.0)

            if jack_client.get_ports('minimixer:', is_input=True):
                print('JACK Minimixer started')
            else:
                raise(EnvironmentError("Could not start minimixer"))
        else:
            print('Connecting to existing minimixer instance.')

        jack_client.close()

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

        for stimulus_name, stimulus in StimuliList.items():
            if stimulus['Type'] == 'Background':
                self.BackgroundSounds[stimulus_name] = SoundStimulus(stimulus, file_root, osc_port, verbose)
                #visualization.add_zone_position(0, VirtualTrackLength, fillcolor=stimulus['Color'], width=0.5, alpha=0.75)
            elif stimulus['Type'] == 'Beep':
                self.Beeps[stimulus_name] = BeepSound(stimulus, file_root, osc_port, verbose)
            elif stimulus['Type'] == 'Localized':
                if not track_length:
                    raise(ValueError('SoundStimulus: Illegal to define a "Localized" sound without defining the Maze->Length.'))
                # visualization.add_zone_position(stimulus['CenterPosition'] - stimulus['Modulation']['Width']/2, 
                #                     stimulus['CenterPosition'] + stimulus['Modulation']['Width']/2, 
                #                     fillcolor=stimulus['Color'])
                self.LocalizedStimuli[stimulus_name] = LocalizedSound(track_length, stimulus, file_root, osc_port, verbose)

            time.sleep(0.25)
        
    def update_beeps(self, time):
        for _, beep in self.Beeps.items():
                beep.update(time)

    def update_localized(self, pos):
        for _, sound in self.LocalizedStimuli.items():
            sound.pos_update_gain(pos)        

    def close_process(self):
        if self.p_minimix:
            self.p_minimix.kill()

    def __del__(self):
        self.close_process()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        for _, stimulus in self.BackgroundSounds.items():
            stimulus.close_processes()
        for _, stimulus in self.Beeps.items():
            stimulus.close_processes()
        for _, stimulus in self.LocalizedStimuli.items():
            stimulus.close_processes()
        self.close_process()



class SoundStimulus():
    def __init__(self, stimulus_params, file_root, osc_port, verbose):
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
        if file_root is not None:
            filename = os.path.join(file_root, filename)
        if not os.path.isfile(filename):
            raise(ValueError("Sound file {} could not be found.".format(filename)))
        else:
            if verbose > 1:
                print('Loading: {}'.format(filename))

        if 'MinimixChannel' in stimulus_params:
            channel = stimulus_params['MinimixChannel'].lower()
            if channel not in ['left', 'right']:
                raise(ValueError("MinimixChannel should be 'left' or 'right'."))
        else:
            channel = 'left'

        if 'MinimixInputPort' in stimulus_params:
            self.inputPort = stimulus_params['MinimixInputPort']
            portName = 'minimixer:in{}_{}'.format(self.inputPort,channel)
            if jack_client.get_all_connections(portName):
                raise(ValueError("Specified port {} is already connected".format(portName)))
        else: # Auto assign a new minimxer port to this stimulus
            availablePortNames = [p.name for p in jack_client.get_ports('minimixer:', is_input=True)]
            if availablePortNames is None:
                raise(EnvironmentError("Jack minimix appears not to be running."))

            self.inputPort = None
            inputPort = 1

            portName = 'minimixer:in{}_{}'.format(inputPort,channel)            
            while portName in availablePortNames:
                if not jack_client.get_all_connections(portName):
                    self.inputPort = inputPort
                    break;
                else:
                    inputPort = inputPort + 1
                    portName = 'minimixer:in{}_{}'.format(inputPort,channel)
            
        if not jack_client.get_ports(portName):
            raise(EnvironmentError("Not enough minimixer ports. Restart with 'MaximumNumberOfStimuli' of at least {}".format(inputPort)))
        else:
            if (verbose > 1):
                print('Input port: {}'.format(self.inputPort))

        jack_client.close()

        jackplay_cmd = ['/usr/local/bin/sndfile-jackplay', '-l0', '-a=minimixer:in{}_{}'.format(self.inputPort,channel), '{}'.format(filename)]
        if (verbose > 1):
            print(jackplay_cmd)
        
        if verbose > 2:
            self.p_jackplay = Popen(jackplay_cmd)
        else:
            self.p_jackplay = Popen(jackplay_cmd, stdout=DEVNULL, stderr=DEVNULL)

        time.sleep(0.25)

        
        self.gain = self.baseline_gain

        self.oscC = OSCClient('127.0.0.1', int(osc_port))
        self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), self.gain])


    def change_gain(self, gain):
        if gain != self.gain:
            self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), gain])
            self.gain = gain

    def close_processes(self):
        if self.p_jackplay:
            self.p_jackplay.kill()

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

