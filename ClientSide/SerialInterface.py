
import serial
import struct

class SerialInterface():
    def __init__(self, SerialPort='/dev/ttyS0', version=2):
        self.version = version
        self.serialPort = SerialPort

        self.GPIOs = {}

        self.GPIO_state = b'\x00'

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
            StartChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO  = struct.unpack('<cBLhlBx', x)
            assert(StartChar == self.startChar)
            return StartChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO

        elif (self.version==2):
            StartChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO  = struct.unpack('<cBLhlHHx', x)
            assert(StartChar == self.startChar)
            return StartChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO, AuxGPIO


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
        #self.serial.flush()
        #self.serial.flushOutput()


    def raise_output(self, GPIO):
        pin = self.GPIOs[GPIO]['Number']
        if (self.version == 1):
            data = (self.GPIO_state[0] | (0x1 << pin)).to_bytes(1, byteorder='big',signed=True)
            self.GPIO_state = data
            self.send_byte(data)
        elif (self.version == 2):
            self.write_pin(pin, 1, pinType='DIO', mirror=self.GPIOs[GPIO]['Mirror'])


    def lower_output(self, GPIO):
        pin = self.GPIOs[GPIO]['Number']
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
                                 `Type` - `Input` or `Output`
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

