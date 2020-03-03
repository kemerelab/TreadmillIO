# Configuring tasks controlled with the Treadmill-IO module

The file `AuditoryVR.py` generates a behavioral control system which has the following abilities:
  - Logs data acquired from the IO module
  - Processes incoming rotational encoder data to map wheel position to virtual position
  - Presents auditory stimuli in one of three modalities: background sounds, cues triggered by task states, and the sound of acoustic landmarks (which are amplitude modulated by their distance to the mouse in virtual space)
  - Responds appropriately to GPIO inputs (i.e., licks) based on task logic
  - Triggers GPIO output pulses as appropriate (i.e., to drive a syringe pump)

The controller is configued by a YAML file. An example configuration file, with explanatory comments is below.

```yaml
Info: # "Info" configuration options can be overridden by command line options
  MouseID: V1A1 # Used to name saved data file
  Note: '' # Added in a block at the start of saved data file
  Session: '' # This is added to default (date and time)
  TaskType: 3tones-change-classical

Preferences:
  HeartBeat: 250 # The interval at which a heart-beat info message is printed to screen (in ms) 
  SoundResourcesDirectory: '/home/ckemere/Code/TreadmillTracker/ClientSide/Tasks/HeadFixedTask/Sounds' # Directory in which file is stored



GPIO: # A list of GPIO pins used in the task
  Lick: # This is an arbitrary label used later to configure Reward
    Number: 3 # This is the pin number from the board
    Type: 'Input_Pulldown' # Pin type is either 'Inout' or 'Output'; special cases could be 'Input_Pulldown' or 'Input_Pullup' 
                           # (where the pull-down/pull-up resistors are enabled).
    Power: True # The 'Power' option is for 'Input' type GPIOs. It configures whether the Aux-GPIO is set to high, 
                # enabling the power channel of the audio jack.
  Reward:
    Number: 4
    Type: 'Output'
    Mirror: True # The 'Mirror' option is for 'Output' type GPIOs. It configures whether the associated Aux-GPIO pin is raised/lowered 
                 # whenver the GPIO itself is. The Aux-GPIO is connected to an LED, which allows for visualization of the GPIO state.

Maze:
  Type: 'VR' # VR or physical
  EncoderGain: 4096.0 # Encoder value per revolution
  Length: 150.0 # Length of the track. Presumably in cm units, but units don't really matter as long as they're consistent.
  WheelDiameter: 20.2 # Diameter of the wheel (presumably in cm units).
  TrackTransform: None # Not currently implemented.

AuditoryStimuli:
  Defaults: # Default values for stimulus parameters
    Filename: '' # Possible to specify a default sound file
    BaselineGain: 0.0 # Volume of stimulus. Corresponds to the peak volume for a 'Localized' stimulus 
    Type: 'Localized' # 'Localized' (landmark), 'Background', or 'Beep'
    Modulation: # Parameters which define how 'Localized' stimuli are spatially-modulated
      Type: Linear # Currently only 'Linear'
      CenterPosition: 0.0 # Position of Localized stimulus in VR space
      Width: 25 # cm in which sound is on (full width)
      #Rate: -20.0 # dB/cm - NOT CURRENTLY IMPLEMENTED BUT WOULD BE NICE FOR THE FUTURE
      CutoffGain: -60.0 #dB at cutoff - The change in gain as a function of position is determined
                        #  by the Width, BaselineGain, and CutoffGain parameters.
                        #  Note that true "Off" corresponds in our system to -90 dB.
                        #  So depending on SNR and perceptual ability, a CutoffGain greater
                        #  than that value might be noticeable.  

  StimuliList:
    BackgroundSound: # This label is abitrary. In the case of "Beep" stimuli, it is used to configure Reward
      Type: 'Background' # Stimuli type - 'Localized', 'Background', or 'Beep'
      BaselineGain: -5.0
      Filename: 'pink_noise.wav'
      Color: 'pink' # Matplotlib color name used for visualization system
    Zone_1:
      CenterPosition: 12.5 
      Filename: 'tone_3kHz.wav'
      Modulation:
        Width: 10
      Color: 'lime'
    Zone_2:
      CenterPosition: 102.5 
      Filename: 'tone_11kHz.wav'
      Modulation:
        Width: 25
      Color: 'orange'
    RewardSound:
      Type: 'Beep'
      Filename: 'tone_11kHz.wav'

RewardZones: # Configuration of Reward locations
  RewardZoneList:
    Reward1: # Arbitrary label
      Type: 'Operant' # Currently either "Classical" or "Operant" corresponding to
                      # the definitions from psychology. Classical rewards are delivered
                      # at a particular location regardless of animal behavior. Operant
                      # rewards require a GPIO trigger (which we call a "Lick")
      LickPin: 'Lick' # Label of GPIO for sensor which triggers reward (in the case of Operant-style tasks)
      DispensePin: 'Reward' # (Required!) Label of GPIO for output pin which should trigger reward dispensing. 
      PumpRunTime: 1000 # How long to run the reward pump for. Note that this is also the duration
                        # of time that any associated Beep will be played.
      LickTimeout: 3000.0 # Time between reward availability
      MaxSequentialRewards: 50 # Number of times an animal that has stopped in the reward zone
                               # can be rewarded without having to exit and re-enter. After reaching
                               # this number of rewards, the animal has to pass through the "ResetZone"
                               # to reset reward availability.
      RewardZoneStart: 145 # The reward location begins at this point (in track coordinates).
                        # Note that since the track loops around, the end can be before the 
                        # beginning. (Order of beginning and end matter!)
      RewardZoneEnd: 30 # The reward zone ends at this point.
      ResetZoneStart: 100 # The start of location of the zone in the track that primes this reward location.
      ResetZoneEnd: 130 # The end of the reset zone.
      Color: 'black' # Visualization color of the reward zone.
      RewardSound: 'RewardSound' # The name of the auditory stimulus (of type "Beep") which should be played 
                                 # at the time of reward. This plays for the same duration of the pulse which
                                 # triggers the pump.



```