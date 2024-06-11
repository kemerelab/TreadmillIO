import serial
import argparse
import yaml
import time

# Command-line arguments
parser = argparse.ArgumentParser(description='Demo a task by manually changing GPIO pins.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyACM0',
                   help='TTY device for USB-serial interface (e.g., /dev/ttyUSB0 or COM10)')
parser.add_argument('-C','--param-file', default='defaults.yaml',  
                    help='YAML file containing task parameters')
parser.add_argument('--version', default=2, type=int, choices=[1, 2],
                    help='Demo version to use.')
args = parser.parse_args()

# Get GPIO config
with open(args.param_file, 'r') as f:
    config = yaml.safe_load(f)['GPIO']

if args.version == 1:
    raise EnvironmentError('Version 1 no longer supported.')
elif args.version != 2:
    raise ValueError('Unknown version {}.'.format(args.version))

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
print(len(x))
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

# Configure GPIO pins
gpio = {}
for gpio_label, gpio_config in config.items():
    if gpio_config.get('Type', 'INPUT').upper() != 'OUTPUT':
        raise EnvironmentError('All GPIO pins must be configured to OUTPUT.')

    gpio[gpio_label] = {}
    gpio[gpio_label]['Number'] = gpio_config['Number']
    gpio[gpio_label]['Mirror'] = gpio_config.get('Mirror', False)

    # Create serial message to configure pin
    msg = b'\xA9' # message init
    msg += b'C' # config flag
    msg += gpio[gpio_label]['Number'].to_bytes(1, byteorder='big',signed=True)
    msg += int(1).to_bytes(1, byteorder='big',signed=True)
    
    # Send message
    n = Interface.write(msg)

# Main loop
while (True):
    # Wait for input
    print('Enter pin label and value: <pin_label> <0, 1> (<time ms>)')
    p = input().split(' ')
    assert len(p) in [2, 3]
    label = p[0]
    val = int(p[1])
    if len(p) == 3:
        duration = float(p[2])
    else:
        duration = -1
    if val not in [0, 1]:
        raise ValueError('Value must be 0 or 1.')
    elif label not in gpio:
        raise ValueError('Pin {} not found.'.format(label))

    # Create serial message
    msg = b'\xA9'
    if gpio[label]['Mirror']:
        msg += b'M'
    else:
        msg += b'D'
    msg += gpio[label]['Number'].to_bytes(1, byteorder='big',signed=True)
    msg += val.to_bytes(1, byteorder='big',signed=True)

    # Send message
    n = Interface.write(msg)
    
    # Set duration if specified
    t = time.time()
    if duration >= 0.0:
        time.sleep(duration/1000.0)
        n = Interface.write(msg[:-1] + ((val+1)%2).to_bytes(1, byteorder='big', signed=True))
        print('Set pin {} to {} for {} ms.'.format(label, val, duration))      
    else:
        print('Set pin {} to {}.'.format(label, val))