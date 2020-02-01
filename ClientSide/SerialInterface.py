
import serial
import struct

class SerialInterface():
    def __init__(self, SerialPort='/dev/ttyS0', version=2):
        self.version = version

        print('Connecting to serial/USB interface {} and synchronizing.'.format(SerialPort))
        self.serial = serial.Serial(port=SerialPort,
            baudrate = 256000,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.2
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
        assert(len(x) == self.MessageLen*(K+1))
        # print(x) # useful for debugging....
        # Find offset in this set
        index = 0
        while(True):
            print(x[index:])
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

        print('Found index: {}'.format(index))

        x = self.serial.read(index) # read the last little bit of the bad block, and we are in sync!


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

        configureString += bytes({pin})
        assert(direction in self.PinModes)
        configureString += bytes({self.PinModes[direction]})
        self.serial.write(configureString)

    def write_pin(self, pin, value, pinType='DIO'):
        writeString = b'\xA9' # Magic character which indicates start of command
        if pinType == 'DIO':
            writeString += b'D'
        elif pinType == 'AUX':
            writeString += b'A'

        writeString += bytes({pin})
        writeString += bytes({value})
        print(writeString)
        self.serial.write(writeString)
