import serial
import argparse
import yaml

# Command-line arguments
parser = argparse.ArgumentParser(description='Demo a task by manually changing GPIO pins.')
parser.add_argument('-P', '--serial-port', default='/dev/ttyACM0',
                   help='TTY device for USB-serial interface (e.g., /dev/ttyUSB0 or COM10)')
parser.add_argument('-C','--param-file', default='defaults.yaml',  
                    help='YAML file containing task parameters')
args = parser.parse_args()

# Get GPIO config
with open(args.param_file, 'r') as f:
    config = yaml.safe_load(f)['GPIO']

gpio = {}
for gpio_label, gpio_config in config.items():
    if gpio_config.get('Type', 'INPUT').upper() != 'OUTPUT':
        raise EnvironmentError('All GPIO pins must be configured to OUTPUT.')

    gpio[gpio_label] = {}
    gpio[gpio_label]['Number'] = gpio_config['Number']
    gpio[gpio_label]['Mirror'] = gpio_config.get('Mirror', False)

# Create serial interface
Interface = serial.Serial(args.serial_port,
                          baudrate=256000,
                          parity=serial.PARITY_NONE,
                          stopbits=serial.STOPBITS_ONE,
                          bytesize=serial.EIGHTBITS,
                          timeout=0.1,
                          write_timeout=0)

# Main loop
while (True):
    # Wait for input
    print('Enter pin label and value (0 or 1).')
    label, val = input().split(' ')
    val = int(val)
    if val not in [0, 1]:
        raise ValueError('Value must be 0 or 1.')
    elif label not in gpio:
        raise ValueError('Pin {} not found.'.format(label))

    # Create serial message
    msg = b'\xA9'
    print(msg)
    if gpio[label]['Mirror']:
        msg += b'M'
    else:
        msg += b'D'
    msg += gpio[label]['Number'].to_bytes(1, byteorder='big',signed=True)
    msg += val.to_bytes(1, byteorder='big',signed=True)
    print(msg)

    # Send message
    n = Interface.write(msg)

    print('Set pin {} to {}.'.format(label, val))


