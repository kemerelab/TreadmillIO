import time
import numpy as np
from itertools import cycle
import warnings

class TaskState:
    def __init__(self, currentStateLabel, nextStateLabel):
        self.Type = None
        self.NextState = nextStateLabel
        self.Label = currentStateLabel

class DelayState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, Params):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Delay'

        if (Params['Duration'] == 'Exponential'):
            self.rate = Params['Rate']
            self.delay_min = Params['Min']
            self.delay_max = Params['Max']
            
            delays = np.random.exponential(self.rate,size=(50,))
            delays += self.delay_min
            delays[delays > self.delay_max] = self.delay_max
            self.delays = np.rint(delays).astype('int').tolist()
        elif (Params['Duration'] == 'Fixed'):
            self.delays = [Params['Value']]
        else:
            raise(NotImplementedError("Random durations other than exponential not yet implemented"))

        self.DelayList = cycle(self.delays)
        
    def getDelay(self):
        return next(self.DelayList)


class VisualizationState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, Params):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Visualization'

        self.visType = Params['VisType']
        if self.visType == 'Fixed':
            self.command = Params['Command']
        elif self.visType == 'Random':
            self.command = []
            self.command_probs = []
            prob_total = 0
            for stim_name, stim in Params['Options'].items():
                prob_total += stim['Probability']
                self.command.append(stim['Command'])
                self.command_probs.append(stim['Probability'])
            self.command_probs = [p / prob_total for p in self.command_probs]
            self.command_choices = np.random.choice(range(len(self.command_probs)), 
                    5000, True, self.command_probs)
            self.CommandIndices = cycle(self.command_choices)
    
    def getVisualizationCommand(self):
        if self.visType == 'Fixed':
            return self.command
        elif self.visType == 'Random':
            return self.command[next(self.CommandIndices)]

class RewardState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, Params, serialInterface, beeps):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Reward'

        self.serialInterface = serialInterface

        if Params['DispensePin'] not in serialInterface.GPIOs:
            raise ValueError('Dispense pin not in defined GPIO list')
        if ('RewardSound' in Params) and (Params['RewardSound'] != 'None'):
            if Params['RewardSound'] not in beeps:
                raise ValueError('Reward sound not in defined Beeps list')

        self.RewardPin = Params['DispensePin']
        if 'PumpRunTime' in Params:
            self.PulseLength = Params['PumpRunTime']
        else:
            self.PulseLength = 250 # ms
        if 'RewardSound' in Params:
            self.RewardSound = Params['RewardSound']
        else:
            self.RewardSound = None

        self.EventTimer = 0

    def startExecution(self):
        self.serialInterface.raise_output(selfRewardPin)
        if self.RewardSound:
            Beeps[self.RewardSound].change_gain(stimulus['BaselineGain'])

    def endExecution(self):
        self.serialInterface.lower_output(self.RewardPin)
        if self.RewardSound:
            Beeps[self.RewardSound].change_gain(stimulus['BaselineGain'])



    def rewardValues(self):
        return self.RewardPin, self.PulseLength, self.RewardSound

class SetGPIOState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, params, serial_interface):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'SetGPIO'

        if params['Pin'] not in serial_interface.GPIOs:
            raise ValueError('GPIO pin not in defined GPIO list')

        self.Pin = params['Pin']
        self.Value = params['Value']

    def getPinValue(self):
        return self.Pin, self.Value


def create_state_machine(config, serial_interface, beeps):
    StateMachineDict = {}
    FirstState = None

    if not(serial_interface):
        warnings.warn('StateMachine being created without GPIO (gpio_names is empty).',
                       SyntaxWarning)


    for state_name, state in config.items():
        if 'FirstState' in state and state['FirstState']:
            FirstState = state_name

        if (state['Type'] == 'Delay'):
            StateMachineDict[state_name] = DelayState(state_name, state['NextState'], state['Params'])

        elif (state['Type'] == 'SetGPIO'):
            StateMachineDict[state_name] = SetGPIOState(state_name, state['NextState'], state['Params'], serial_interface)

        elif (state['Type'] == 'Reward'):
            StateMachineDict[state_name] = RewardState(state_name, state['NextState'], state['Params'], 
                                                       serial_interface, beeps)

        elif (state['Type'] == 'Visualization'):
            StateMachineDict[state_name] = VisualizationState(state_name, state['NextState'], state['Params'])

        else:
            raise(NotImplementedError("State machine elements other than " 
                    "Delay, SetGPIO, Reward, or Visualization not yet implemented"))

    if FirstState is None:
        FirstState = list(StateMachineDict.keys())[0]
        print('First state in state machine not defined. '
            'Picking first state in list: {}'.format(FirstState))
    else:
        print('First state is {}'.format(FirstState))

    return StateMachineDict, FirstState


class TaskStateMachine():
  def __init__(self, config, serialInterface=None, auditoryStimuli=None):
    
    self.StateMachineDict = {}
    self.FirstState = None
    self.EnableSound = bool(auditoryStimuli) # test if empty

    if not(serialInterface):
        warnings.warn('StateMachine being created without GPIO (gpio_names is empty).',
                       SyntaxWarning)

    # ---------------- Process YAML config file / dictionary -------------------------------------------
    for state_name, state in config.items():
        if 'FirstState' in state and state['FirstState']:
            FirstState = state_name

        if (state['Type'] == 'Delay'):
            self.StateMachineDict[state_name] = DelayState(state_name, state['NextState'], state['Params'])

        elif (state['Type'] == 'SetGPIO'):
            if state['Params']['Pin'] not in gpio_names:
                raise ValueError('GPIO pin not in defined GPIO list')
            self.StateMachineDict[state_name] = SetGPIOState(state_name, state['NextState'], state['Params'])

        elif (state['Type'] == 'Reward'):
            self.StateMachineDict[state_name] = RewardState(state_name, state['NextState'], state['Params'])

        elif (state['Type'] == 'Visualization'):
            self.StateMachineDict[state_name] = VisualizationState(state_name, state['NextState'], state['Params'])

        else:
            raise(NotImplementedError("State machine elements other than " 
                    "Delay, SetGPIO, Reward, or Visualization not yet implemented"))

    if FirstState is None:
        FirstState = list(StateMachineDict.keys())[0]
        print('First state in state machine not defined. '
            'Picking first state in list: {}'.format(FirstState))
    else:
        print('First state is {}'.format(FirstState))

    
    self.RewardPumpEndTime = 0
    self.RewardPumpActive = False

    self.StateMachineWaiting = False
    self.StateMachineWaitEndTime = 0




