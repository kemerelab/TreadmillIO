import time
import numpy as np
from itertools import cycle
import warnings
import zmq


class TaskState:
    def __init__(self, currentStateLabel, nextStateLabel):
        self.Type = None
        self.NextState = nextStateLabel
        self.Label = currentStateLabel

    def execute():
        pass


class DelayState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, Params):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Delay'

        if (Params['Duration'] == 'Exponential'):
            self.rate = Params['Rate']
            self.delay_min = Params['Min']
            self.delay_max = Params['Max']

            delays = np.random.exponential(self.rate, size=(50,))
            delays += self.delay_min
            delays[delays > self.delay_max] = self.delay_max
            self.delays = np.rint(delays).astype('int').tolist()
        elif (Params['Duration'] == 'Fixed'):
            self.delays = [Params['Value']]
        else:
            raise(NotImplementedError(
                "Random durations other than exponential not yet implemented"))

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
    def __init__(self, currentStateLabel, nextStateLabel, params, io_interface, sound_controller):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Reward'

        print(sound_controller)

        self.io_interface = io_interface

        if params['DispensePin'] not in io_interface.GPIOs:
            raise ValueError('Dispense pin not in defined GPIO list')

        if ('RewardSound' in params) and (params['RewardSound'] != 'None'):
            if params['RewardSound'] not in sound_controller.Beeps:
                raise ValueError('Reward sound not in defined Beeps list')

        self.RewardPin = params['DispensePin']
        if 'PumpRunTime' in params:
            self.PulseLength = params['PumpRunTime']
        else:
            self.PulseLength = 250  # ms
        if 'RewardSound' in params:
            self.RewardSound = params['RewardSound']
        else:
            self.RewardSound = None

        self.EventTimer = 0

    def rewardValues(self):
        return self.RewardPin, self.PulseLength, self.RewardSound


class SetGPIOState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, params, io_interface):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'SetGPIO'

        if (params['Pin'] not in io_interface.GPIOs) or (io_interface.GPIOs[params['Pin']]['Type'] != 'Output'):
            raise ValueError('TaskState SetGPIO Pin not specified as a GPIO output.')

        self.Pin = params['Pin']
        self.Value = params['Value']

    def getPinValue(self):
        return self.Pin, self.Value
        

class TaskStateMachine():
    def __init__(self, config, io_interface=None, sound_controller=None):

        self.zmq_context = None # keep track of whether we'll do comms

        self.StateMachineDict = {}
        self.FirstState = None

        self.needs_zmq = False

        if not(io_interface):
            self.io_interface = None
            warnings.warn('StateMachine being created without GPIO (no io_interface specified).',
                          SyntaxWarning)
        else:
            self.io_interface = io_interface


        if not(sound_controller):
            self.sound_controller = None
            warnings.warn('StateMachine being created without GPIO (no SoundController specified).',
                          SyntaxWarning)
        else:
            self.sound_controller = sound_controller

        # ---------------- Process YAML config file / dictionary -------------------------------------------
        for state_name, state in config['States'].items():
            if 'FirstState' in state and state['FirstState']:
                self.FirstState = state_name

            if (state['Type'] == 'Delay'):
                self.StateMachineDict[state_name] = DelayState(
                    state_name, state['NextState'], state['Params'])

            elif (state['Type'] == 'SetGPIO'):
                self.StateMachineDict[state_name] = SetGPIOState(
                    state_name, state['NextState'], state['Params'], io_interface)

            elif (state['Type'] == 'Reward'):
                print(sound_controller)
                self.StateMachineDict[state_name] = RewardState(
                    state_name, state['NextState'], state['Params'], io_interface, sound_controller)

            elif (state['Type'] == 'Visualization'):
                self.StateMachineDict[state_name] = VisualizationState(
                    state_name, state['NextState'], state['Params'])
                self.needs_zmq = True

            else:
                raise(NotImplementedError("State machine elements other than "
                                          "Delay, SetGPIO, Reward, or Visualization not yet implemented"))

        if self.FirstState is None:
            self.FirstState = list(self.StateMachineDict.keys())[0]
            print('First state in state machine not defined. '
                  'Picking first state in list: {}'.format(self.FirstState))
        else:
            print('First state is {}'.format(self.FirstState))

        self.StateMachineWaiting = False
        self.StateMachineWaitEndTime = 0

        self.CurrentState = self.StateMachineDict[self.FirstState]


        if self.needs_zmq:
            self.zmq_context = zmq.Context()
            if 'VisualCommsPort' in config:
                self.port = str(config['VisualCommsPort'])
            else:
                self.port = "5556"


    def __enter__(self):
        self.socket = self.zmq_context.socket(zmq.PAIR)
        self.socket.connect("tcp://localhost:%s" % self.port)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.socket.close()

    def start(self, time):
        if (self.CurrentState.Type == 'Delay'):
            self.StateMachineWaitEndTime = time + self.CurrentState.getDelay()
            self.StateMachineWaiting = True


    def update_statemachine(self, time, logger=None):
        if self.StateMachineWaiting:  # Currently in a `Delay` or other state in which we shouldn't transition yet
            if time > self.StateMachineWaitEndTime:
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]
                self.StateMachineWaiting = False
            else:
                pass
        else:
            if self.CurrentState.Type == 'Delay':
                delay = self.CurrentState.getDelay()
                self.StateMachineWaitEndTime = time + delay
                self.StateMachineWaiting = True
                if logger:
                    logger([time,-1,-1,-1,-1,'Delay', delay])

            elif self.CurrentState.Type == 'SetGPIO':
                pin, level = self.CurrentState.getPinValue()
                if level:
                    self.io_interface.raise_output(pin)
                else:
                    self.io_interface.lower_output(pin)
                if logger:
                    logger([time,-1,-1,-1,-1,'SetGPIO', pin, level])
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

            elif self.CurrentState.Type == 'Reward':
                pin, duration, beep_name = self.CurrentState.rewardValues()
                self.io_interface.pulse_output(pin, time + duration)
                print('Reward!')
                if self.sound_controller:
                    self.sound_controller.Beeps[beep_name].play(time)
                if logger:
                    logger([time,-1,-1,-1,-1,'Reward', pin, duration])
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

            elif self.CurrentState.Type == 'Visualization':
                command = self.CurrentState.getVisualizationCommand()
                if logger:
                    logger([time,-1,-1,-1,-1,'Visualization', command])
                self.socket.send_string(command)
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

