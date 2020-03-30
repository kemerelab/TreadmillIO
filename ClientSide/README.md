# Configuring tasks controlled with the Treadmill-IO module


## Auditory VR Tasks

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
  AudioFileDirectory: '/home/ckemere/Code/TreadmillTracker/ClientSide/Tasks/HeadFixedTask/Sounds' # Directory in which file is stored
  MaximumNumberOfStimuli: 10 # Maximum number of auditory stimuli which follow in the StimuliList
  OscPort: 12345 # TCP port to use for OSC communication with jackminimix
  Defaults: # Default values for stimulus parameters
    Filename: '' # Possible to specify a default sound file
    BaselineGain: 0.0 # Volume of stimulus. Corresponds to the peak volume for a 'Localized' stimulus 
    OffGain: -90.0 # dB for stimulus off. -90 dB corresponds to 0 for jackminimix
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
      MinimixInputPort: 1 # jackminimix channel to use. By default, these will be auto-assigned if not specified
      MinimixChannel: 'left' # stereo audio channel whose volume should be controlled for this stimulus
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


## StateMachine or VisualStimulus Tasks
The file `VisualStimulusExperiment.py` executes a state machine. Critically one of the states sends commands to a 
visual stimulus server started by executing `VisualStimulusServer.py`. Currently, the `VisualStimulusServer.py` file
creates a grey screen and presents a flashing checkerboard either in the left or right visual hemifields (calibrated
for a large 40" curved display). Following is an example YAML configuration file:

```
Info: # "Info" configuration options can be overridden by command line options
  MouseID: V1A1 # Used to name saved data file
  Note: '' # Added in a block at the start of saved data file
  Session: '' # This is added to default (date and time)
  TaskType: Moana Classical Conditioning

Preferences:
  HeartBeat: 1000 # The interval at which a heart-beat info message is printed to screen (in ms) 
  AudioFileDirectory: '/home/ckemere/Code/TreadmillTracker/ClientSide/Tasks/HeadFixedTask/Sounds' # Directory in which file is stored
  RandomSeed: 345
  VisualCommsPort: 5556
  LogCommands: True


GPIO: # A list of GPIO pins used in the task
  Camera: # This is an arbitrary label used later to configure Reward
    Number: 1 # This is the pin number from the board
    Type: 'Input_Pulldown' 
    Power: False
  Lick: # This is an arbitrary label used later to configure Reward
    Number: 2 # This is the pin number from the board
    Type: 'Input_Pulldown' # Pin type is either 'Input' or 'Output'; special cases could be 'Input_Pulldown' or 'Input_Pullup' 
                           # (where the pull-down/pull-up resistors are enabled).
    Power: True # The 'Power' option is for 'Input' type GPIOs. It configures whether the Aux-GPIO is set to high, 
                # enabling the power channel of the audio jack.
  ScreenLeft: # This is an arbitrary label used later to configure Reward
    Number: 3 # This is the pin number from the board
    Type: 'Input_Pulldown' 
    Power: True

  ScreenRight: # This is an arbitrary label used later to configure Reward
    Number: 4 # This is the pin number from the board
    Type: 'Input_Pulldown' 
    Power: True
  Reward:
    Number: 5
    Type: 'Output'
    Mirror: True # The 'Mirror' option is for 'Output' type GPIOs. It configures whether the associated Aux-GPIO pin is raised/lowered 
                 # whenver the GPIO itself is. The Aux-GPIO is connected to an LED, which allows for visualization of the GPIO state.
  GreyScreenIO:
    Number: 6
    Type: 'Output'
    Mirror: True 
  Disable7:
    Number: 7
    Type: 'Input_Disable'
  Disable8:
    Number: 8
    Type: 'Input_Disable'
  Disable9:
    Number: 9
    Type: 'Input_Disable'
  Disable10:
    Number: 10
    Type: 'Input_Disable'
  Disable11:
    Number: 11
    Type: 'Input_Disable'
  Disable12:
    Number: 12
    Type: 'Input_Disable'              

Maze:
  Type: 'StateMachine'

StateMachine: # Note - will start at the state below with the parameter "FirstState: True". Otherwise
              # the first state listed will be first.
  BlankScreen:
    Type: 'Visualization'
    Params:
      VisType: 'Fixed' # Can be either "Fixed" or "Random"
      Command: 'GREY'  # Command string sent to VisualStimulusServer
    NextState: 'Raise'
  Raise: # Raise a GPIO during the grey screen period
    Type: 'SetGPIO'
    Params:
      Pin: 'GreyScreenIO'
      Value: 1
    NextState: 'Intertrial'
  Intertrial:
    Type: 'Delay'
    Params:
      Duration: 'Fixed' # Can be either "Fixed" or "Random"
      Value: 5000
    NextState: 'Lower'
  Lower:
    Type: 'SetGPIO'
    Params:
      Pin: 'Reward'
      Value: 0
    NextState: 'StimulusPresentation'
  StimulusPresentation:
    FirstState: True    # Start statemachine here!s
    Type: 'Visualization'
    Params:
      VisType: 'Random' # Random visualizations are currently uniformly distributed based on the specified
                        # relative probabilities.
      Options:
        Right:
          Command: 'RIGHT' # Command sent to VisualStimulusServer
          Probability: 1   # Relative probabilitity. These will be normalized by the sum of all options.
        Left:
          Command: 'LEFT'
          Probability: 1
    NextState: 'StimulusPresentationDelay'
  StimulusPresentationDelay:
    Type: 'Delay'
    Params:
      Duration: 'Exponential' # Random duration is a bounded exponential.
      Rate: 1000              # Rate of exponential distribution in ms.
      Min: 2000               # Minimum value added to samples from distribution.
      Max: 4000               # All samples are truncated to this value.
    NextState: 'Reward'
  Reward:
      Type: 'Reward'   # We could also trigger reward by using the SetGPIO command. The "Reward" states
                       # are 'non-blocking', meaning the state machine will move along to the next state.
      NextState: 'BlankScreen'
      Params:
        DispensePin: 'Reward' # (Required!) Label of GPIO for output pin which should trigger reward dispensing. 
        PumpRunTime: 100 # How long to run the reward pump for. Note that this is also the duration
                          # of time that any associated Beep will be played.
        RewardSound: 'RewardSound' # The name of the auditory stimulus (of type "Beep") which should be played 
                              # at the time of reward. This plays for the same duration of the pulse which
                              # triggers the pump.

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
    RewardSound:
      Type: 'Beep'
      Filename: 'tone_11kHz.wav'
```