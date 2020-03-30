import time
from subprocess import Popen, DEVNULL
import jack # pip install JACK-client
from oscpy.client import OSCClient
import os

class SoundStimulus():
    def __init__(self, stimulus_params, general_prefs):
        self.p_minimix = None

        #start jack with = ['/usr/bin/jackd', '--realtime', '-P10','-d', 'alsa', '-p128', '-n2', '-r48000']
        #self.p_jack = Popen(jack_cmd, stdout=DEVNULL, stderr=DEVNULL)

        try:
            self.jack_client = jack.Client('PythonJackClient', no_start_server=True)
        except jack.JackError:
            raise(EnvironmentError("Jack Client not started"))

        filename = stimulus_params['Filename']
        if general_prefs['AudioFileDirectory']:
            filename = os.path.join(general_prefs['AudioFileDirectory'], filename)
        if not os.path.isfile(filename):
            raise(ValueError("Sound file {} could not be found.".format(filename)))
        else:
            print('Loading: {}'.format(filename))


        if 'MaximumNumberOfStimuli' in general_prefs:
            totalStimuli = general_prefs['MaximumNumberOfStimuli']
        else:
            totalStimuli = 10

        if 'OscPort' in general_prefs:
            osc_port = general_prefs['OscPort']
        else:
            osc_port = 12345

        # Handle the minimixer already running
        if not self.jack_client.get_ports('minimixer:', is_input=True): # minimix not started
            minimix_cmd  = ['/usr/local/bin/jackminimix', '-a', '-c', str(totalStimuli), '-p', str(osc_port)]
            self.p_minimix = Popen(minimix_cmd)

            for i in range(5):
                if self.jack_client.get_ports('minimixer:', is_input=True):
                    break
                time.sleep(1.0)

            if self.jack_client.get_ports('minimixer:', is_input=True):
                print('JACK Minimixer started')
            else:
                raise(EnvironmentError("Could not start minimixer"))
        else:
            print('Connecting to existing minimixer instance.')

        if 'MinimixChannel' in stimulus_params:
            channel = stimulus_params['MinimixChannel'].lower()
            if channel not in ['left', 'right']:
                raise(ValueError("MinimixChannel should be 'left' or 'right'."))
        else:
            channel = 'left'

        if 'MinimixInputPort' in stimulus_params:
            self.inputPort = stimulus_params['MinimixInputPort']
            portName = 'minimixer:in{}_{}'.format(self.inputPort,channel)
            if self.jack_client.get_all_connections(portName):
                raise(ValueError("Specified port {} is already connected".format(portName)))
        else: # Auto assign a new minimxer port to this stimulus
            availablePortNames = [p.name for p in self.jack_client.get_ports('minimixer:', is_input=True)]
            if availablePortNames is None:
                raise(EnvironmentError("Jack minimix appears not to be running."))

            self.inputPort = None
            inputPort = 1

            portName = 'minimixer:in{}_{}'.format(inputPort,channel)            
            while portName in availablePortNames:
                if not self.jack_client.get_all_connections(portName):
                    self.inputPort = inputPort
                    break;
                else:
                    inputPort = inputPort + 1
                    portName = 'minimixer:in{}_{}'.format(inputPort,channel)
            
        if not self.jack_client.get_ports(portName):
            raise(EnvironmentError("Not enough minimixer ports. Restart with 'MaximumNumberOfStimuli' of at least {}".format(inputPort)))
        else:
            print('Input port: {}'.format(self.inputPort))

        jackplay_cmd = ['/usr/local/bin/sndfile-jackplay', '-l0', '-a=minimixer:in{}_{}'.format(self.inputPort,channel), '{}'.format(filename)]
        print(jackplay_cmd)
        

        self.p_jackplay = Popen(jackplay_cmd, stdout=DEVNULL, stderr=DEVNULL)
        time.sleep(0.25)

        self.oscC = OSCClient('127.0.0.1', int(osc_port))
        self.gain = -10.0
        self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), self.gain])

        self.baseline_gain = stimulus_params['BaselineGain']
        if 'OffGain' in stimulus_params:
            self.off_gain = stimulus_params['OffGain']
        else:
            self.off_gain = -90.0 



    def change_gain(self, gain):
        if gain != self.gain:
            self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), gain])
            self.gain = gain

    def close_processes(self):
        self.p_jackplay.kill()
        time.sleep(0.25)
        if self.p_minimix:
            self.p_minimix.kill()
            time.sleep(0.25)

    def __del__(self):
        self.close_processes()


class LocalizedSound(SoundStimulus):
    def __init__(self, stimulus_params, general_prefs, track_length):
        SoundStimulus.__init__(stimulus_params, general_prefs)

        self.center = stimulus_params['CenterPosition']
        self.width = stimulus_params['Modulation']['Width']
        self.half = self.width/2
        self.trackLength = track_length
        self.maxGain = stimulus_params['BaselineGain']
        self.minGain = stimulus_params['Modulation']['CutoffGain']

    def linear_gain_from_pos(self, pos):
        relpos = (pos - self.center) % self.trackLength
        if (relpos  > self.trackLength / 2):
            relpos = relpos - self.trackLength
        elif (relpos < -self.trackLength / 2):
            relpos = relpos + self.trackLength
        if (abs(relpos) > self.half):
            return self.offGain
        else:
            return (1 - abs(relpos/self.half)) * (self.maxGain - self.minGain) + self.minGain

    def pos_update_gain(self, pos):
        relpos = (pos - self.center) % self.trackLength
        if (relpos  > self.trackLength / 2):
            relpos = relpos - self.trackLength
        elif (relpos < -self.trackLength / 2):
            relpos = relpos + self.trackLength
        if (abs(relpos) > self.half):
            new_gain = self.offGain
        else:
            new_gain = (1 - abs(relpos/self.half)) * (self.maxGain - self.minGain) + self.minGain

        change_gain(new_gain)




def create_sound_stimuli(config, track_length=None):
    print('Normalizing stimuli:')
    StimuliList = config['StimuliList']
    for stimulus_name, stimulus in StimuliList.items(): 
        print(' - ',stimulus_name)
        for key, config_item in config['Defaults'].items():
            if key not in stimulus:
                stimulus[key] = config_item
            elif isinstance(config_item, dict):
                for subkey, sub_config_item in config_item.items():
                    if subkey not in stimulus[key]:
                        stimulus[key][subkey] = sub_config_item


    BackgroundSounds = {}
    Beeps = {}
    SoundStimuliList = {}

    for stimulus_name, stimulus in StimuliList.items():
        if stimulus['Type'] == 'Background':
            BackgroundSounds[stimulus_name] = SoundStimulus(stimulus, config)
            visualization.add_zone_position(0, VirtualTrackLength, fillcolor=stimulus['Color'], width=0.5, alpha=0.75)
            BackgroundSounds[stimulus_name].change_gain(stimulus['BaselineGain'])
        elif stimulus['Type'] == 'Beep':
            Beeps[stimulus_name] = SoundStimulus(stimulus, config)
            Beeps[stimulus_name].change_gain(stimulus['BaselineGain'])
            Beeps[stimulus_name].change_gain(-90.0) # beep for a very short moment
        elif stimulus['Type'] == 'Localized':
            if not track_length:
                raise(ValueError('Illegal to define a "Localized" sound without defining the Maze->Length.'))
            visualization.add_zone_position(stimulus['CenterPosition'] - stimulus['Modulation']['Width']/2, 
                                stimulus['CenterPosition'] + stimulus['Modulation']['Width']/2, 
                                fillcolor=stimulus['Color'])
            SoundStimuliList[stimulus_name] = LocalizedSound(stimulus, config, track_length)
            SoundStimuliList[stimulus_name].change_gain(-90.0) # start off turned off

        time.sleep(1.0)

    return BackgroundSounds, Beeps, SoundStimuliList