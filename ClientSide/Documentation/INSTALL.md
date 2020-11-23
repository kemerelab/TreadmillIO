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

#### For webcam interface, we are using code from pupil-labs. It requires a non-standard version of libuvc
This needs `cmake` and `libusb-1.0-0-dev` as dependencies, as well as the turboJPEG headers

`sudo apt install libusb-1.0-0-dev cmake libjpeg-turbo8-dev libturbojpeg0-dev` 

`git clone https://github.com/pupil-labs/libuvc`

As per the instructions on their github page:
```
git clone https://github.com/pupil-labs/libuvc
cd libuvc
mkdir build
cd build
cmake .. 
make && sudo make install
```

I found some wierdness where for some reason I didn't get all the dependencies
compiled in the first time. I haven't been able to replicate this though.

We compress the video, which requires `ffmpeg`:

`sudo apt install ffmpeg`

For some odd reason, the pupil-labs version of libuvc fails for camera resolutions of 1080p or greater (see [unresolved issue on github](https://github.com/pupil-labs/pyuvc/issues/73)). The issue appears to be the estimation of the bandwidth size of packets from the webcams using their custom bandwidth factor. (see https://github.com/pupil-labs/libuvc/blob/master/src/stream.c#L1038-L1048) This causes a problem at higher bandwidths, such as 1080p, because 1) a bandwidth factor that is too large (>= 4) will create a maximum per packet usage that is larger than all alt-settings (leading to here), but 2) a bandwidth factor that is too small (< 4) will cause some weird JPEG file header error (from who knows where). To fix this, simply comment out their custom code to estimate the config_bytes_per_packet (prior to building!), using the original code in the line above instead. 


#### Clone the `TreadmillIO` repository

`git clone https://github.com/kemerelab/TreadmillIO`

Install further dependencies:
`pip3 install zmq pyserial soundfile gitpython` (for main code)

`pip3 install cython setproctitle scikit-video pyglet` (for uvc camera interface)

If you will use the camera interface, 
```
cd TreadmillIO/ClientSide/treadmillio/uvccam
python3 setup.py build_ext --inplace
```
(This last command compiles the cython-based camera interface code.)

#### Install the required files for the Teensy interface:
Optionally download the Arduino package and the Teensy installation files from
[https://www.pjrc.com/teensy/td_download.html].

Install the udev rules copied from this website in
[Documentation/49-teensy.rules] to `/etc/udev/rules.d`.

If you will use the camera interface, you'll need to make a rules file for your
camera. Look for it in `lsusb` and find out the vendor and product IDs. It will
look something like this:

`Bus 003 Device 002: ID 05a3:9422 ARC International Camera`

05a3 is the vendor id and 9422 is the product id. Then add a line in the example
rules file [Documentation/10-libuvc.rules] and copy it to `/etc/udev/rules.d`.

After you update the UDEV rules, you'll need to restart it by either restarting
your computer or running:

`udevadm control --reload-rules && udevadm trigger`

You'll probably need to unplug and replug the devices after that for them to
be picked up.

#### Test
You should now be able to plug in the IO board and run `./RunExperiment.py` with
an appropriate configuration file.  For example: 
`./RunExperiment.py -C ExampleConfigs/latency_test.yaml`.

