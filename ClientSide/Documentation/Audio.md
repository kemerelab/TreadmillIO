# Optional audio setup on Linux
While the following instructions have been tested on Ubuntu 20.04, they should work for most Linux distros.

## Disable PulseAudio
On many Linux systems, including Ubuntu, sounds takes the following path from app to speaker:

    app -> PulseAudio -> ALSA -> soundcard

PulseAudio acts as a higher-level interface for ALSA and, on Ubuntu, is heavily used for most interfaces (it is what is used in Settings > Sound). While useful for general purposes, you may want to disable it for a couple of reasons: 1) it can grab our soundcard in unexpected ways (leading to a "Device or resource busy" error), and 2) it requires an additional layer of configuration if customizing sound interface (which we will do with ALSA below). Note, however, that disabling PulseAudio will stop many apps from properly streaming audio.

To disable, run:

```shell
pulseaudio --kill
```

and check with:

```shell
ps -ef | grep pulse
```

If processes are still running, then PulseAudio may be automatically restarted. Try the following:

1. Open/create a configuration file: `vim ~/.config/pulse/client.conf`
2. Insert `autospawn = no` and save file.

If the above doesn't work, stop `systemctl` from launching it: 
    
```shell
systemctl --user stop pulseaudio.socket
systemctl --user stop pulseaudio.service
```

PulseAudio can be restarted by undoing the above:

```shell
systemctl --user start pulseaudio.socket
systemctl --user start pulseaudio.service
pulseaudio --start
```

## Set default sound device
The second step in releasing our sound device from other apps (ensuring that `TreadmillIO` will have exclusive access to it) is to set another soundcard as default for ALSA. We first create an ALSA configuration file:

```shell
vim ~/.asoundrc
```

and then paste the following:

```
pcm.!default {
    type hw
    card Generic
}

ctl.!default {
        type hw
        card Generic
}
```

where `Generic` is replaced with the name or number of the card you are NOT using for `TreadmillIO` (e.g. the built-in card). (For information about how to extract card names/numbers and device numbers, see below.) We could additionally add the device number under `card` to be more specific, or we could change the default PCM type to be something other than `hw` by creating a PCM slave:

```
pcm_slave.builtin {
    pcm "hw:Generic,0"
    channels 2
}

pcm.!default {
    type plug
    slave builtin

}

ctl.!default {
    type hw
    card Generic
}
```

## Finding soundcard info
To specify which soundcard and device to use for `TreadmillIO`, we must know the card number and device number we'd like to use. We can determine what capabilities our machine has by looking at the output of a couple of commands:

```shell
aplay -l
**** List of PLAYBACK Hardware Devices ****
card 0: Generic [HD-Audio Generic], device 0: ALC1220 Analog [ALC1220 Analog]
Subdevices: 1/1
Subdevice #0: subdevice #0
card 0: Generic [HD-Audio Generic], device 1: ALC1220 Digital [ALC1220 Digital]
Subdevices: 1/1
Subdevice #0: subdevice #0
card 1: SoundCard [Xonar SoundCard], device 0: USB Audio [USB Audio]
Subdevices: 1/1
Subdevice #0: subdevice #0
card 1: SoundCard [Xonar SoundCard], device 1: USB Audio [USB Audio #1]
Subdevices: 1/1
Subdevice #0: subdevice #0
card 1: SoundCard [Xonar SoundCard], device 2: USB Audio [USB Audio #2]
Subdevices: 1/1
Subdevice #0: subdevice #0
card 1: SoundCard [Xonar SoundCard], device 3: USB Audio [USB Audio #3]
Subdevices: 1/1
Subdevice #0: subdevice #0
...
```

Here, we see our soundcards listed in the format `card #: <name> (<description>), device #: <description>`, along with some other data. These are the card numbers/names and device numbers that ALSA uses. One other piece of information, the PCM type, comes from another command:

```shell
aplay -L
...
default
sysdefault:CARD=Generic
    HD-Audio Generic, ALC1220 Analog
    Default Audio Device
front:CARD=Generic,DEV=0
    HD-Audio Generic, ALC1220 Analog
    Front speakers
...
sysdefault:CARD=SoundCard
    Xonar SoundCard, USB Audio
    Default Audio Device
front:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    Front speakers
surround21:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    2.1 Surround output to Front and Subwoofer speakers
surround40:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    4.0 Surround output to Front and Rear speakers
surround41:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    4.1 Surround output to Front, Rear and Subwoofer speakers
surround50:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    5.0 Surround output to Front, Center and Rear speakers
surround51:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    5.1 Surround output to Front, Center, Rear and Subwoofer speakers
surround71:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    7.1 Surround output to Front, Center, Side, Rear and Woofer speakers
...
hw:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    Direct hardware device without any conversions
hw:CARD=SoundCard,DEV=1
    Xonar SoundCard, USB Audio #1
    Direct hardware device without any conversions
hw:CARD=SoundCard,DEV=2
    Xonar SoundCard, USB Audio #2
    Direct hardware device without any conversions
hw:CARD=SoundCard,DEV=3
    Xonar SoundCard, USB Audio #3
    Direct hardware device without any conversions
plughw:CARD=SoundCard,DEV=0
    Xonar SoundCard, USB Audio
    Hardware device with all software conversions
plughw:CARD=SoundCard,DEV=1
    Xonar SoundCard, USB Audio #1
    Hardware device with all software conversions
plughw:CARD=SoundCard,DEV=2
    Xonar SoundCard, USB Audio #2
    Hardware device with all software conversions
plughw:CARD=SoundCard,DEV=3
    Xonar SoundCard, USB Audio #3
    Hardware device with all software conversions
...
```

Here, we see a line not only for each device of each card, but also for each PCM type of that device, which is the text prior to `:`. The PCM type tells ALSA what format to expect from the app sending data to the soundcard. For instance, `front` would expect two channels (left and right), `surround51` would expect five channels (front left, front right, center, rear, subwoofer), and so on. The most basic PCM type is `hw`, which tells ALSA not to modify the data coming from the app when sending to the soundcard. This is typically what we'll use for a one- or two-speaker setup (but we could extend to more by using `surround51`, for example). We use the combination of card number/name and device number to specify where to direct our audio output, or on the other side, where to grab our audio input (which can be found analogously by using `arecord -l` and `arecord -L`). We place this designation in the `HWDevice` parameter for each device in our `DeviceList`. We can use one of several formats, such as `hw:<card #>,<device #>` or `hw:CARD=<card name>, DEVICE=<device #>`.

While cards and devices have many features, an important one is the sampling rate(s) that are available for capture devices. We need to know the specific capabilities of each device so that we don't set the `SamplingRate` parameter in our configuration file to one that is not available on that capture device. To see what sampling rates are available, first actively record from the device (such as running `RunExperiment.py`), and then try the following:

```shell
cat /proc/asound/card0/pcm0c/sub0/hw_params
```

Note that the directories under `/proc/asound` may have to be modified for the specific capture device you are investigating; simply dig around in the directory to find it.

## Resources
Here are some helpful links to learn more about Linux audio:

https://www-uxsup.csx.cam.ac.uk/pub/doc/suse/suse9.0/userguide-9.0/
https://www.volkerschatz.com/noise/alsa.html
https://www.alsa-project.org/wiki/Main_Page
https://www.alsa-project.org/wiki/Asoundrc
https://alsa.opensrc.org/Asoundrc
http://delogics.blogspot.com/2014/11/understanding-alsa-device-subdevice-and.html