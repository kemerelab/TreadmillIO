
![TreadmillIO IO Module](http://github.com/kemerelab/TreadmillIO/blob/master/treadmillio-interface-pcb.jpg)

# TreadmillIO

The TreadmillIO project (which needs a better name!) combines a simple USB-based
data IO module with a Python framework to provide a way to control behavioral
experiments using a simple YAML-based configuration scheme. One particular focus
of the project is to receive input from a rotary encoder to control auditory 
stimuli in a VR environment, but it is also convenient to use for experiments in
freely moving animals. In conjunction with the 
[PyRenderMaze project](http://github.com/ckemere/PyRenderMaze), a simple OpenGL-based
visual VR environment can easily be deployed. 

### Requirements
The software is currently tested on Ubuntu Linux. The low-latency audio framework
relies on ALSA, which is Linux only, and the UVC WebCam capture interface has
only been tested on Linux. However, the project should otherwise work across
platforms. Pull requests for Windows or MAC compiling are welcome.

See the [installation instructions for the software framework](ClientSide/Documentation/INSTALL.md) to get up
and running.

Some example [configuration files](ClientSide/ExampleConfigFiles/) are available.