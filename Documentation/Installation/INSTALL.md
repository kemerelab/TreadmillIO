# Installation

### !!Update!!! TreadmillIO should now be compatible with pip
Start with a clean Python environment. For example:
```
mamba create -n treadmillio python=3.10
conda activate treadmillio
```

Install using `pip` from Github:
```
pip install git+https://github.com/kemerelab/TreadmillIO/
```

### Install the required files for the Teensy hardware interface:
Optionally download the Arduino package and the Teensy installation files from
[https://www.pjrc.com/teensy/td_download.html].

#### For Linux:
Install the udev rules copied from this website in
[Documentation/00-teensy.rules] to `/etc/udev/rules.d`.

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

### Test
You should now be able to plug in the IO board and run `run-treadmillio` with
an appropriate configuration file.  For example: 
`./RunExperiment.py ExampleConfigs/tests/test_io_pins.yaml`. (This should 
activate all the IO pins on your interface board.)

```
run-treadmillio -P /dev/tty.usbmodem86825701 /path/to/TreadmillIO/Documentation/ExampleConfigs/tests/test_io_pins.yaml
```

## Optional sound interface using the Alsa library
Install the dependency of `pyalsaaudio`

`sudo apt install libasound2-dev`

Install `pyalsaaudio`

`pip install pyalsaaudio`

#### Test
You should now be able to plug in the IO board and run `run-treadmillio` with
an appropriate configuration file. For example: 
`run-treadmillio /path/to/TreadmillIO/Documents/ExampleConfigs/tests/test_sound.yaml`. 
(This should play different sounds through the left and right channels of the stereo interface.)
Note that you will need to set what the listed `HWDevice` in the config file is.
You can use the command `aplay -L` to list all the devices present in your system.

## Optional Webcam video recording: 
This submodule interfaces with webcams detected by the kernel. It assumes that a
MJPEG stream is available and automatically asks for that (this works for most Logitech
and no-name cameras). By default the file that is saved will thus be a MJPEG file
(which basically means a series of JPEGS).

#### We are using code from pupil-labs. It requires a non-standard version of libuvc
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


#### Next, we need to compile the cython code that operates the camera

I found some wierdness where for some reason I didn't get all the dependencies
compiled in the first time. I haven't been able to replicate this though.

We compress the video, which requires `ffmpeg`:

`sudo apt install ffmpeg`

For some odd reason, the pupil-labs version of libuvc fails for camera resolutions of 1080p or greater (see [unresolved issue on github](https://github.com/pupil-labs/pyuvc/issues/73)). The issue appears to be the estimation of the bandwidth size of packets from the webcams using their custom bandwidth factor. (see https://github.com/pupil-labs/libuvc/blob/master/src/stream.c#L1038-L1048) This causes a problem at higher bandwidths, such as 1080p, because 1) a bandwidth factor that is too large (>= 4) will create a maximum per packet usage that is larger than all alt-settings (leading to here), but 2) a bandwidth factor that is too small (< 4) will cause some weird JPEG file header error (from who knows where). To fix this, simply comment out their custom code to estimate the config_bytes_per_packet (prior to building!), using the original code in the line above instead. 

`pip3 install cython scikit-video pyglet` (specifically for uvc camera interface)

Next, change to the `uvccam` subdirectory `cd TreadmillIO/src/treadmillio/uvccam`. Then run

```
python3 setup.py build_ext --inplace
```
(This last command compiles the cython-based camera interface code.)

#### Test
You should now be able to plug in the IO board and run `run-treadmillio` with
an appropriate configuration file. For example: 
`run-treadmillio ExampleConfigs/tests/test_webcam.yaml`. This should pop up
a window that shows the current view of the world. Note that f you have mulitple
webcams connected, you might need to change what the listed `CameraIndex` in the 
config file is. There are hooks via the `CameraParams` section of the configuration
to set parameters of the camera.

Note that in the `/path/to/TreadmillIO/src/treadmillio/uvccam`, you can also execute
just the webcam submodule by running `python3 uvccam.py`.

## Option GigE machine vision camera recording:
#### We use the Aravis GiGE library to communicate with a wide variety of cameras (Basler, Allied Vision, and Lucid Labs)

Aravis has a number of dependencies. This seems to capture it:

`sudo apt install meson libgirepository1.0-dev libxml2-dev libgtkmm-3.0-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-0 gettext`

`git clone https://github.com/AravisProject/aravis` (We have tested with version 0.82!)

Aravis uses the meson build system. The instructions here describe the process:
[https://aravisproject.github.io/docs/aravis-0.8/aravis-building.html](https://aravisproject.github.io/docs/aravis-0.8/aravis-building.html).
Basically, you:
```
meson build
cd build
ninja
ninja install
```

By default the python libraries are installed in `/usr/local/lib`. So the last critical
step to making Aravis useful to us is to link them into `/usr/lib`. (You could also
change the installation directory!)
```
ln -s /usr/local/lib/x86_64-linux-gnu/girepository-1.0/Aravis-0.8.typelib /usr/lib/x86_64-linux-gnu/girepository-1.0/
```

#### Test Aravis
If everything went right, you should have compiled the Viewer application. You should be able to run it:
```
cd aravis/build/viewer
./arv-viewer-0.8
```
Make sure you can see your camera and that it opens

**With the Allied Vision camera we tested, it had to be opened in the Vimba application
before Aravis could get data from it!**

Now, install the python packages need for the submodule.

`sudo apt install python3-opencv`

(I hate to depend on OpenCV, but it seems to be best for de-bayering color sensor raw data.)

`pip3 install pyglet simplejpeg`

#### Test
You should now be able to plug in the IO board and run `run-treadmillio` with
an appropriate configuration file. For example: 
`run-treadmillio ExampleConfigs/tests/test_webcam.yaml`. This should pop up
a window that shows the current view of the world. If you have multiple GigE cameras
in your system, it should be possible to interface them selectively, but this has
not yet been implemented. Note that the config file specifies the size of the window
to be captured and an offset from the bounds of the full sensor. `Offset` and `Res` 
have to sum to less than the full sensor size to work. Currently only `Mono8` and
`Bayer_RG8` formats are supported, though more could be added. If `Compress` is `True`
we JPEG compress. Otherwise, the raw video is stored!

Note that in the `TreadmillIO/src/treadmillio/camera`, you can also execute
just the webcam submodule by running `python3 gigecam.py`.
