import time
from subprocess import Popen, DEVNULL
import jack # pip install JACK-client
from oscpy.client import OSCClient
import os

class LocalizedSound():
    def __init__(self, center, width, trackLength, maxGain, minGain, offGain=-90.0):
        self.center = center
        self.width = width
        self.half = width/2
        self.trackLength = trackLength
        self.maxGain = maxGain
        self.minGain = minGain
        self.offGain = offGain

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


class SoundStimulus():
    def __init__(self, filename=None, inputPort=None, channel='left', osc_port=12345, totalStimuli=10):
        self.p_minimix = None

        #start jack with = ['/usr/bin/jackd', '--realtime', '-P10','-d', 'alsa', '-p128', '-n2', '-r48000']
        #self.p_jack = Popen(jack_cmd, stdout=DEVNULL, stderr=DEVNULL)

        try:
            self.jack_client = jack.Client('PythonJackClient', no_start_server=True)
        except jack.JackError:
            raise(EnvironmentError("Jack Client not started"))

        if not os.path.isfile(filename):
            raise(ValueError("Sound file {} could not be found.".format(filename)))

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


        if filename is not None:
            if inputPort:
                portName = 'minimixer:in{}_{}'
                if self.jack_client.get_all_connections(portName):
                    raise(ValueError("Specified port {} is already connected".format(portName)))
            else:
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
                    raise(EnvironmentError("Not enough minimixer ports. Restart with totalStimuli of at least {}".format(inputPort)))
                else:
                    print('Input port: {}'.format(self.inputPort))

            jackplay_cmd = ['/usr/local/bin/sndfile-jackplay', '-l0', '-a=minimixer:in{}_{}'.format(self.inputPort,channel), '{}'.format(filename)]
            print(jackplay_cmd)
        

        self.p_jackplay = Popen(jackplay_cmd, stdout=DEVNULL, stderr=DEVNULL)
        time.sleep(0.25)

        self.oscC = OSCClient('127.0.0.1', int(osc_port))
        self.gain = -10.0
        self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), self.gain])

        self.localized = None


    def change_gain(self, gain):
        if gain != self.gain:
            self.oscC.send_message(b'/mixer/channel/set_gain',[int(self.inputPort), gain])
            self.gain = gain


    def initLocalizedSound(self, center, width, trackLength, maxGain, minGain, offGain=-90.0):
        self.localized = LocalizedSound(center, width, trackLength, maxGain, minGain, offGain)

    def pos_update_gain(self, pos):
        if self.localized:
            new_gain = self.localized.linear_gain_from_pos(pos)
            self.change_gain(new_gain)

    def close_processes(self):
        self.p_jackplay.kill()
        time.sleep(0.25)
        if self.p_minimix:
            self.p_minimix.kill()
            time.sleep(0.25)

    def __del__(self):
        self.close_processes()

    