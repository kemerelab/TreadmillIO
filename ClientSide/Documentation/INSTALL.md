# Installation

### Required Dependencies
This has been tested from a clean installation of Ubuntu 20.04. The following
packages should be installed via `apt`:

`sudo apt install python3-pip python3-numpy python3-matplotlib python3-scipy python3-pygraphviz`

`sudo apt install git`

#### Clone the `ckemere` version of `pyalsaaudio` and install it

`git clone https://github.com/ckemere/pyalsaaudio`

Install the dependency of `pyalsaaudio`

`sudo apt install libasound2-dev`

In the `pyalsaaudio` installation directory run: `pip3 install -e .`
The installation should conlcude without error.

#### Clone the `TreadmillIO` repository

`git clone https://github.com/kemerelab/TreadmillIO`

Install further dependencies:
`pip3 install zmq pyserial soundfile gitpython`

#### Install the required files for the Teensy interface:
Optionally download the Arduino package and the Teensy installation files from
[https://www.pjrc.com/teensy/td_download.html].

Install the udev rules copied from this website in
[Documentation/49-teensy.rules] to `/etc/udev/rules.d`.

#### Test
You should now be able to plug in the IO board and run `./RunExperiment.py` with
an appropriate configuration file.

