
#import serial

from itertools import cycle
import csv
import time

class SerialInterface():

    def __init__(self, SerialPort='/dev/ttyS0'):
        self.GPIO_state:bytes = b'\x00' # initialize GPIO state to 0

        self.EncoderData = []
        self.GPIOData = []

        self.MasterTime = 0 # supposed to be a 4 byte int

        # Load a sample data file
        print('Loading sample data file for simulation.')
        with open('shorterlog.txt', newline='') as csvfile: 
            reader = csv.reader(csvfile, delimiter=',') 
            for row in reader: 
                self.EncoderData.append(int(row[2])) # Append the (wrapped) Encoder data
                self.GPIOData.append(int(row[1])) # Append the (wrapped) Encoder data


        self.UnwrappedEncoder = self.EncoderData[0] # supposed to be an unsigned 4 byte int
        self.Encoder = self.EncoderData[0] # supposed to be a 2 byte int
        self.EncoderGenerator = cycle(self.EncoderData) # make it circular
        self.GPIOGenerator = cycle(self.GPIOData) # make it circular
        self.Clock = time.monotonic()


        self.GPIO_pin_reset_callbacks = []


    def send_byte(self, data: bytes):
        if data is not None:
            if isinstance(data, bytes) and len(data) == 1:
                self.GPIO_state = bytes(data)
            else:
                raise(ValueError('data was not a length 1 byte.'))


    def read_data(self):
        FlagChar = b'E'
        StructSize = 14
        self.MasterTime = self.MasterTime + 2 # 2 ms ticks
        NextEncoder = next(self.EncoderGenerator)
        DiffEncoder = NextEncoder - self.Encoder
        if DiffEncoder > 2048:
            DiffEncoder = DiffEncoder - 4096
        elif DiffEncoder < -2048:
            DiffEncoder = DiffEncoder + 4096
        self.UnwrappedEncoder += DiffEncoder
        self.Encoder = NextEncoder
        
        NextGPIOData = next(self.GPIOGenerator)
        MaskedGPIO = (NextGPIOData | self.GPIO_state[0]).to_bytes(1, byteorder='little')

        #FlagChar, StructSize, MasterTime, Encoder, UnwrappedEncoder, GPIO  = struct.unpack('<cBLhlBx', x)
        # c = char, B = unsigned char, L = unsigned long (4 bytes), h = short (2 bytes), l = long, x = pad byte
        assert(FlagChar == b'E')

        currentClock = time.monotonic()
        while (currentClock - self.Clock) < 0.002:
            time.sleep((0.002 - (currentClock-self.Clock))*0.8)
            currentClock = time.monotonic()
        self.Clock = currentClock


        return_value = FlagChar, StructSize, self.MasterTime, self.Encoder, self.UnwrappedEncoder, MaskedGPIO

        data = b'\x00'
        active_callbacks = [c for c in self.GPIO_pin_reset_callbacks if self.MasterTime >= c[0]]
        if active_callbacks:
            for c in active_callbacks:
                data = bytes( data[0] | (1 << c[1]) )
            self.GPIO_pin_reset_callbacks[:] = [c for c in self.GPIO_pin_reset_callbacks if self.MasterTime < c[0]]
            self.send_byte(data)

        return return_value


    def gpio_pulse(self, pin, duration):
        # (1) change pin value
        # (2) register a value change for the future
        data = bytes(self.GPIO_state[0] | (1 << pin))
        offtime = self.MasterTime + duration
        self.send_byte(data)
        self.GPIO_pin_reset_callbacks.append( (offtime, pin) )