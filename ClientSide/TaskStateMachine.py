import time
import numpy as np
from itertools import cycle

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
    def __init__(self, currentStateLabel, nextStateLabel, Params):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Reward'

        self.RewardPin = Params['DispensePin']
        if 'PumpRunTime' in Params:
            self.PulseLength = Params['PumpRunTime']
        else:
            self.PulseLength = 250 # ms
        if 'RewardSound' in Params:
            self.RewardSound = Params['RewardSound']
        else:
            self.RewardSound = None

    def rewardValues(self):
        return self.RewardPin, self.PulseLength, self.RewardSound

class SetGPIOState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, Params):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'SetGPIO'

        self.Pin = Params['Pin']
        self.Value = Params['Value']

    def getPinValue(self):
        return self.Pin, self.Value

