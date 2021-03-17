import serial
import argparse
import yaml
import time

# Command-line arguments
parser = argparse.ArgumentParser(description='Demo a task by manually changing GPIO pins.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyACM0',
                   help='TTY device for USB-serial interface (e.g., /dev/ttyUSB0 or COM10)')
parser.add_argument('-p', '--gpio', default=1, type=int,
                    help='GPIO number for syringe pump.')
parser.add_argument('-n', '--num-pulses', default=100, type=int,
                    help='Number of pulses to send.')
parser.add_argument('-t', '--pulse-duration', default=200, type=int,
                    help='Pulse duration in milliseconds.')                
parser.add_argument('--version', default=2, type=int, choices=[1, 2],
                    help='Demo version to use.')
args = parser.parse_args()

# Check parameters
if args.version not in [1, 2]:
    raise ValueError('Unknown version {}.'.format(args.version))
if args.pulse_duration < 125:
    raise UserWarning('Syringe pump may not recognize logic level changes for pulses \
                       near or less than 100 ms.')

# Create serial interface
Interface = serial.Serial(args.serial_port,
                        baudrate=256000,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize=serial.EIGHTBITS,
                        timeout=0.1,
                        write_timeout=0)

# Connect and synchronize
# We read in a large buffer of data and find which offset is the start of the packets
K = 3 # This code works for 100 but not 1000. Maybe related to buffer size???
if (args.version == 1):
    MessageLen = 14
    startChar = b'E'
elif (args.version == 2):
    MessageLen = 17
    startChar = b'F'
x = Interface.read(MessageLen*(K+1))
assert(len(x) == MessageLen*(K+1))
# print(x) # useful for debugging....
# Find offset in this set
index = 0
while(True):
    # print(x[index:])
    continueFlag = False
    for k in range(K):
        if ( x.index(startChar,index + k*MessageLen) - (k*MessageLen + index)) != 0:
            continueFlag = True
    if continueFlag:
        index = index + 1
    else:
        break
    if (index > (MessageLen-1)):
        print('Reached end with bad index')
        assert(False)
        break

x = Interface.read(index) # read the last little bit of the bad block, and we are in sync!

# Configure GPIO pin
gpio = {}

# Create serial message to configure pin
msg = b'\xA9' # message init
msg += b'C' # config flag
msg += args.gpio.to_bytes(1, byteorder='big',signed=True)
msg += int(1).to_bytes(1, byteorder='big',signed=True)

# Send message
n = Interface.write(msg)

# Main loop
for i in range(args.num_pulses):
    if (i+1) % 10 == 0:
        print('Pulse {} of {}...'.format(i+1, args.num_pulses))
    
    # Pulse on
    msg = b'\xA9'
    msg += b'D'
    msg += args.gpio.to_bytes(1, byteorder='big',signed=True)
    msg += int(1).to_bytes(1, byteorder='big',signed=True)
    n = Interface.write(msg)
    time.sleep(args.pulse_duration/1000)

    # Pulse off
    msg = b'\xA9'
    msg += b'D'
    msg += args.gpio.to_bytes(1, byteorder='big',signed=True)
    msg += int(0).to_bytes(1, byteorder='big',signed=True)
    n = Interface.write(msg)
    time.sleep(args.pulse_duration/1000)