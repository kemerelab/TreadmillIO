
from inspect import unwrap # TODO: Remove this???
from re import I # TODO: Remove this???
from numpy.lib.function_base import _unwrap_dispatcher # TODO: Remove this???
import serial
import struct
import warnings
import traceback as tb
from numpy import pi
import numpy as np
import zmq

class SerialInterface():
    def __init__(self, SerialPort='/dev/ttyS0', version=2, gpio_config=None, maze_config=None, zmq_streaming=None):
        self.serial = None
        self.version = version
        self.serialPort = SerialPort

        self.GPIOs = {}

        self.latency = 0

        self.MasterTime = 0
        self.Encoder = 0
        self.unwrapped_encoder = 0
        self.GPIO = None
        self.AuxGPIO = None

        if self.version == 1:
            self.GPIO_state = b'\x00'
        else:
            self.GPIO_state = int(0) # b'\x00'
            self.OutputPinMask = int(0)
            
        if gpio_config is not None:
            for gpio_label, gpio_config in gpio_config.items():
                self.add_gpio(gpio_label, gpio_config)

        self.calculate_position = False
        if maze_config is not None:
            self.calculate_position = True
            self.reinitialize = True
            self.block_movement = False

            self.unwrapped_encoder = 0
            self.initial_encoder = 0
            self.pos = 0
            self.unwrapped_pos = 0

            self.virtual_track_length = maze_config.get('Length', 1000.0) #cm
            self.d = maze_config.get('WheelDiameter', 20.2) #cm
            self.encoder_gain = maze_config.get('EncoderGain', 4096.0)
            self.diameter_constant = pi * self.d / self.encoder_gain

            self.maze_topology = maze_config.get('Topology', 'Ring')
            if self.maze_topology == 'Ring':
                self.maze_topology_fun = lambda x: x % self.virtual_track_length
            elif self.maze_topology == 'Line':
                self.maze_topology_fun = lambda x: min(max(x, 0), self.virtual_track_length)
            else:
                raise(ValueError("Unknown Maze Topology {}. Currently implemented: 'Ring' or 'Line'.".format(self.maze_topology)))

            smoothing_window_length = 50
            self._smoothing_data = np.zeros(smoothing_window_length) # 50 samples at 500 Hz is 0.1 s
            self._smoothing_idx = 0
            self.velocity = 0
        else:
            self.virtual_track_length = 1000.0 #cm

        # We will use the ZMQ PUB/SUB architecture to stream position data
        if zmq_streaming:
            port = zmq_streaming
            context = zmq.Context()
            self.data_socket = context.socket(zmq.PUB)
            self.data_socket.bind("tcp://*:%s" % port)
        else:
            self.data_socket = None


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        print('SerialInterface: exiting because of exception <{}>'.format(exc_type.__name__))
        tb.print_tb(exc_traceback)
        if (self.serial):
            self.serial.close()

    def connect(self):
        print('Connecting to serial/USB interface {} and synchronizing.'.format(self.serialPort))
        self.serial = serial.Serial(port=self.serialPort,
            baudrate = 256000,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.1,
            write_timeout=0
        )

        # Synchronize immediately after opening port!

        # We read in a large buffer of data and find which offset is the start of the packets
        K = 3 # This code works for 100 but not 1000. Maybe related to buffer size???
        if (self.version == 1):
            self.MessageLen = 14
            self.startChar = b'E'
        elif (self.version == 2):
            self.MessageLen = 17
            self.startChar = b'F'
        x=self.serial.read(self.MessageLen*(K+1))
        print(len(x))
        assert(len(x) == self.MessageLen*(K+1))
        # print(x) # useful for debugging....
        # Find offset in this set
        index = 0
        while(True):
            # print(x[index:])
            continueFlag = False
            for k in range(K):
                if ( x.index(self.startChar,index + k*self.MessageLen) - (k*self.MessageLen + index)) != 0:
                    continueFlag = True
            if continueFlag:
                index = index + 1
            else:
                break
            if (index > (self.MessageLen-1)):
                print('Reached end with bad index')
                assert(False)
                break

        # print('Found index: {}'.format(index))

        x = self.serial.read(index) # read the last little bit of the bad block, and we are in sync!

        # Make sure we understand the current state - Configure all pins to be input
        for pin in range(12):
            self.configure_pin(pin+1, 'INPUT')
            self.configure_pin(pin+1, 'INPUT', 'AUX')

        for pin_label, pin in self.GPIOs.items():
            self.configure_io(pin['Number'], pin['Type'], pin['Power'], pin['Mirror'])

        if (self.version == 1):
            self.send_byte(self.GPIO_state) # make sure tracking state and GPIO state variable match!


    def read_data(self):
        x=self.serial.read(self.MessageLen)
        assert(len(x)==self.MessageLen)

        if (self.version==1):
            StartChar, StructSize, self.MasterTime, self.Encoder, new_unwrapped_encoder, \
                    self.GPIO  = struct.unpack('<cBLhlBx', x)
            assert(StartChar == self.startChar)

        elif (self.version==2):
            StartChar, StructSize, self.MasterTime, self.Encoder, new_unwrapped_encoder, \
                    self.GPIO, self.AuxGPIO  = struct.unpack('<cBLhlHHx', x)
            assert(StartChar == self.startChar)
            self.GPIO_state = (self.GPIO_state & self.OutputPinMask) + (self.GPIO & ~self.OutputPinMask)
            if (self.GPIO != self.GPIO_state):
                self.latency = self.latency + 1
                #print(f'Difference between expected and actual GPIO {self.GPIO_state:#0b} {GPIO:#0b}')

        if self.calculate_position or (not self.reinitialize):
            if not self.reinitialize:
                diff_encoder = new_unwrapped_encoder - self.unwrapped_encoder # instantaneous velocity in angle (encoder units)
                if not self.block_movement:
                    change_in_position = diff_encoder * self.diameter_constant # convert velocity to cm per time step
                    self.velocity = self._smooth(change_in_position) * 500 # 500 = Hz samples per second TODO - make a parameter
                    self.unwrapped_pos = self.unwrapped_pos + change_in_position # TODO - why do we need unwrapped_pos anymore???

                    self.pos = self.maze_topology_fun(self.pos + change_in_position) # depending on topology will either wrap or force between 0/track_length
                else:
                    # instantaneous_velocity  = 0
                    # self.unwrapped_pos = self.unwrapped_pos
                    # self.pos = self.pos
                    pass

                self.unwrapped_encoder = new_unwrapped_encoder # update this either way to keep track

            else:
                self.unwrapped_pos = 0
                self.pos = 0
                self.unwrapped_encoder = new_unwrapped_encoder
                self.reinitialize = False
                self.velocity = 0
                
        else:
            self.unwrapped_encoder = new_unwrapped_encoder

        if self.data_socket:
            self.data_socket.send(struct.pack('<Ld', self.MasterTime, self.pos))

        # self.AuxGPIO will be None for version 1 interfaces
        return StartChar, StructSize, self.MasterTime, self.Encoder, self.unwrapped_encoder, self.GPIO, self.AuxGPIO

    def check_latency():
        latency = self.latency
        self.latency = 0
        return latency

    def send_byte(self,data):
        if data is not None:
            self.serial.write(data)

    # Pin Modes from teensy3/core_pins.h
    PinModes = {'INPUT': 0, 
                'OUTPUT': 1,
                'INPUT_PULLUP': 2,
                'INPUT_PULLDOWN': 3,
                'OUTPUT_OPENDRAIN': 4,
                'INPUT_DISABLE': 5}


    def configure_pin(self, pin, direction, pinType='DIO'):
        configureString = b'\xA9' # Magic character which indicates start of command
        if pinType == 'DIO':
            configureString += b'C'
        elif pinType == 'AUX':
            configureString += b'X'

        configureString += pin.to_bytes(1, byteorder='big',signed=True)
        assert(direction.upper() in self.PinModes)
        configureString += self.PinModes[direction.upper()].to_bytes(1, byteorder='big',signed=True)
        self.serial.write(configureString)

    def write_pin(self, pin, value, pinType='DIO', mirror=False):
        writeString = b'\xA9' # Magic character which indicates start of command
        if not mirror:
            if pinType == 'DIO':
                writeString += b'D'
            elif pinType == 'AUX':
                writeString += b'A'
        else:
            writeString += b'M'

        writeString += pin.to_bytes(1, byteorder='big',signed=True)
        writeString += value.to_bytes(1, byteorder='big',signed=True)
        # print(value, writeString) # debuggging
        self.serial.write(writeString)
        
        if (value > 0) : 
            self.GPIO_state |= (0x01 <<pin)
        else:
            self.GPIO_state &= ~(0x01 <<pin)

    def read_pin(self, pin):
        if (self.GPIO & (0x01 << (pin-1))) > 0:
            return True
        else:
            return False

    def raise_output(self, GPIO):
        pin = self.GPIOs[GPIO]['Number']
        if self.GPIOs[GPIO]['IsPulsed']:
            warnings.warn("GPIO pulse raised when already in a pulse.", UserWarning)
        self.GPIOs[GPIO]['IsPulsed'] = False

        if (self.version == 1):
            data = (self.GPIO_state[0] | (0x1 << pin)).to_bytes(1, byteorder='big',signed=True)
            self.GPIO_state = data
            self.send_byte(data)
        elif (self.version == 2):
            self.write_pin(pin, 1, pinType='DIO', mirror=self.GPIOs[GPIO]['Mirror'])


    def lower_output(self, GPIO):
        pin = self.GPIOs[GPIO]['Number']
        self.GPIOs[GPIO]['IsPulsed'] = False
        if (self.version == 1):
            data = (self.GPIO_state[0] & ~(0x1 << pin)).to_bytes(1, byteorder='big',signed=True)
            self.GPIO_state = data
            self.send_byte(data)
        elif (self.version == 2):
            self.write_pin(pin, 0, pinType='DIO', mirror=self.GPIOs[GPIO]['Mirror'])


    def configure_io(self, pin, direction, power=False, mirror=False):
        self.configure_pin(pin, direction, pinType='DIO')
        if (power):
            self.configure_pin(pin, direction='OUTPUT', pinType='AUX')
            self.write_pin(pin, 1, 'AUX')
        if (mirror):
            self.configure_pin(pin, direction='OUTPUT', pinType='AUX')



    def add_gpio(self, name, pin_config):
        """Parse the information associated with a GPIO pin.
        
        Args:
            name: The name which will be associated with the pin for subsequent IO
            pin_config: A dictionary with potential parameters which might be set
                  Required keys: `Number` - the DIO number
                                 `Type` - `Input` or `Output` or `Input_Pullup` or `Input_Pulldown`
                  Optional keys: `Power` - (Boolean) Should the AUX power associated
                                           with the pin be turned on.
                                 `Mirror` - (Boolean) Should the AUX pin associated
                                            with the pin track it's state
        
        """
        self.GPIOs[name] = {'Number':pin_config['Number'], 
                            'Type':pin_config['Type']}

        if 'Power' in pin_config:
            self.GPIOs[name]['Power'] = pin_config['Power']
        else:
            self.GPIOs[name]['Power'] = False

        if 'Mirror' in pin_config:
            self.GPIOs[name]['Mirror'] = pin_config['Mirror']
        else:
            self.GPIOs[name]['Mirror'] = False

        if pin_config['Type'] == 'Output':
            self.OutputPinMask |= 0x01 << pin_config['Number']

        self.GPIOs[name]['IsPulsed'] = False
        self.GPIOs[name]['PulseOffTime'] = -1

    def update_pulses(self):
        for gpio_name, gpio in self.GPIOs.items():
            if gpio['IsPulsed']:
                if (self.MasterTime > gpio['PulseOffTime']):
                    self.lower_output(gpio_name)

    def pulse_output(self, GPIO, off_time):
        # Note: Calling pulse_output when a pulse is already active
        #       will cause the pulse_duration to be updated
        #       Calling raise_output or lower_output on this GPIO subsequently
        #       will cause the pulse to be cancelled.
        self.raise_output(GPIO)
        if (self.GPIOs[GPIO]['IsPulsed']):
            warnings.warn("GPIO pulse instructed when already in a pulse.", UserWarning)
        self.GPIOs[GPIO]['IsPulsed'] = True
        self.GPIOs[GPIO]['PulseOffTime'] = off_time
        

    def _smooth(self, instantaneous_v):
        # Simple moving average filter
        self._smoothing_data[self._smoothing_idx] = instantaneous_v
        self._smoothing_idx = (self._smoothing_idx + 1) % self._smoothing_data.shape[0]
        return self._smoothing_data.mean()
