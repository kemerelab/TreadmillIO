import time
import numpy as np
from itertools import cycle
import warnings
import zmq

import pygraphviz

class TaskState:
    def __init__(self, currentStateLabel, nextStateLabel):
        self.Type = None
        self.NextState = nextStateLabel
        self.label = currentStateLabel

    def get_graph_label(self):
        return '<font point-size="18">{}: <b>{}</b></font>'.format(self.Type, self.label)

    def execute():
        pass


class DelayState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, Params):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Delay'
        self.delay_type = Params['Duration']

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

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        if self.delay_type == 'Fixed':
            return label + '<tr><td>Fixed Delay: {} ms</td></tr></table>'.format(self.delays[0])
        elif self.delay_type == 'Exponential':
            return label + '<tr><td>Exponential Delay: <br/>' \
                '&#955;={} ms (min: {}, max: {}) </td></tr></table>'.format(
                        self.rate, self.delay_min, self.delay_max)
        else:
            return TaskState.get_graph_label(self)
        


class VisualizationState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, params):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Visualization'

        self.visType = params['VisType']
        if self.visType == 'Fixed':
            self.command = params['Command']
        elif self.visType == 'Random':
            self.command = []
            self.command_probs = []
            prob_total = 0
            for stim_name, stim in params['Options'].items():
                prob_total += stim['Probability']
                self.command.append(stim['Command'])
                self.command_probs.append(stim['Probability'])
            self.command_probs = [p / prob_total for p in self.command_probs]
            self.command_choices = np.random.choice(range(len(self.command_probs)),
                                                    5000, True, self.command_probs)
            self.CommandIndices = cycle(self.command_choices)

        #TODO: Validate that server is online

    def getVisualizationCommand(self):
        if self.visType == 'Fixed':
            command = self.command
        elif self.visType == 'Random':
            command = self.command[next(self.CommandIndices)]

        return command

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        if self.visType == 'Fixed':
            return  label + \
                '<tr><td>Sends viz-command: \"{}\"</td></tr></table>'.format(self.command)
        elif self.visType == 'Random':
            return label + '<tr><td>Sends viz-commands: {}<br/>' \
                'with probs: {}</td></tr></table>'.format(
                    self.command, str(self.command_probs))
        else:
            return TaskState.get_graph_label(self)




class RewardState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, params, io_interface, sound_controller):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'Reward'

        self.io_interface = io_interface

        if params['DispensePin'] not in io_interface.GPIOs:
            raise ValueError('Dispense pin not in defined GPIO list')

        if ('RewardSound' in params) and (params['RewardSound'] != 'None'):
            if not sound_controller:
                warnings.warn("RewardState won't produce sound b/c sound is not enabled.", RuntimeWarning)
                self.RewardSound = None
            elif params['RewardSound'] not in sound_controller.Beeps:
                raise ValueError('Reward sound not in defined Beeps list')
            else:
                self.sound_controller = sound_controller
                self.RewardSound = sound_controller.Beeps[params['RewardSound']]
        else:
            self.RewardSound = None

        self.pin = params['DispensePin']
        if 'PumpRunTime' in params:
            self.duration = params['PumpRunTime']
        else:
            self.duration = 250  # ms

    def triggerReward(self, time):
        self.io_interface.pulse_output(self.pin, time + self.duration)
        print('Reward!')
        if self.RewardSound:
            self.RewardSound.play(time)
        return self.pin, self.duration

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        label += '<tr><td>Pulse [{}]({}) for {} ms</td></tr>'.format(
            self.pin,self.io_interface.GPIOs[self.pin]['Number'],self.duration)
        if self.RewardSound:
            label += '<tr><td>Play {}</td></tr>'.format(self.RewardSound.filename)
        label +='</table>'
        return label


class SetGPIOState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, params, io_interface):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'SetGPIO'

        if (params['Pin'] not in io_interface.GPIOs) or (io_interface.GPIOs[params['Pin']]['Type'] != 'Output'):
            raise ValueError('TaskState SetGPIO Pin not specified as a GPIO output.')

        self.pin = params['Pin']
        self.level = params['Value']
        self.io_interface = io_interface

    def setGPIO(self):
        if self.level:
            self.io_interface.raise_output(self.pin)
        else:
            self.io_interface.lower_output(self.pin)

        return self.pin, self.level

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        label += '<tr><td>Set \"{}\"[{}] to {} </td></tr>'.format(self.pin, 
            self.io_interface.GPIOs[self.pin]["Number"],self.level)
        label +='</table>'
        return label


class SetSoundStimulusState(TaskState):
    def __init__(self, currentStateLabel, nextStateLabel, params, sound_controller):
        TaskState.__init__(self, currentStateLabel, nextStateLabel)
        self.Type = 'SetSoundState'

        if ('Sound' not in params) or ('Value' not in params):
            raise(ValueError("SetSoundStimulusState needs a 'Sound' and a 'Value'."))

        if  params['Value'] not in ['On','Off']:
            raise(ValueError("SetSoundStimulusState 'Value' must be 'On' or 'Off'"))

        self.Value = params['Value']
        
        if sound_controller:
            if params['Sound'] not in sound_controller.BackgroundSounds:
                    raise(ValueError('SetSoundStimulusState: "{}" not found in Background sounds list.'.format(params['Sound'])))
            self.Sound = sound_controller.BackgroundSounds[params['Sound']]
            if self.Value == 'On':
                self.gain = self.Sound.baseline_gain
            elif self.Value == 'Off':
                self.gain = self.Sound.off_gain
        else:
            warnings.warn("SetSoundStimulusState won't produce sound bc sound is not enabled.", RuntimeWarning)
            self.Sound = None

    def set_gain(self):
        if self.Sound:
            self.Sound.change_gain(self.gain)

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        if self.Value == 'On':
            label += '<tr><td>Play {}</td></tr>'.format(self.Sound.filename)
        if self.Value == 'Off':
            label += '<tr><td>Stop {}</td></tr>'.format(self.Sound.filename)
        label +='</table>'
        return label





class TaskStateMachine():
    def __init__(self, config, io_interface=None, sound_controller=None):

        self.zmq_context = None # keep track of whether we'll do comms

        self.StateMachineDict = {}
        self.FirstState = None

        self.needs_zmq = False
        self.socket = None

        if not(io_interface):
            self.io_interface = None
            warnings.warn('StateMachine being created without GPIO (no io_interface specified).',
                          RuntimeWarning)
        else:
            self.io_interface = io_interface


        if not(sound_controller):
            self.sound_controller = None
            warnings.warn('StateMachine being created without sound (no SoundController specified).',
                          RuntimeWarning)
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

            elif (state['Type'] == 'SetSoundState'):
                self.StateMachineDict[state_name] = SetSoundStimulusState(
                    state_name, state['NextState'], state['Params'], sound_controller)

            elif (state['Type'] == 'Reward'):
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
        if self.needs_zmq:
            self.socket = self.zmq_context.socket(zmq.PAIR)
            self.socket.connect("tcp://localhost:%s" % self.port)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.socket:
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
                pin, level = self.CurrentState.setGPIO()
                if logger:
                    logger([time,-1,-1,-1,-1,'SetGPIO', pin, level])
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

            elif self.CurrentState.Type == 'SetSoundState':
                if self.sound_controller:
                    self.CurrentState.set_gain()
                if logger:
                    # TODO: log which sound and which level!
                    logger([time,-1,-1,-1,-1,'SetSoundState'])
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

            elif self.CurrentState.Type == 'Reward':
                pin, duration = self.CurrentState.triggerReward(time)
                if logger:
                    logger([time,-1,-1,-1,-1,'Reward', pin, duration])
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

            elif self.CurrentState.Type == 'Visualization':
                command = self.CurrentState.getVisualizationCommand()
                self.socket.send_string(command)

                if logger:
                    logger([time,-1,-1,-1,-1,'Visualization', command])
                self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]


    def render(self, filename):
        G = pygraphviz.AGraph(directed=True, rankdir='LR', type='UTF-8')
        for state_name, state in self.StateMachineDict.items():
            G.add_node(state.label, label='<'+state.get_graph_label()+'>',shape='box')
        for state_name, state in self.StateMachineDict.items():
            G.add_edge(state.label, self.StateMachineDict[state.NextState].label)
        
        G.node_attr.update(fontname='helvetica', fontsize="10")
        G.edge_attr.update(len=3)
        G.layout('neato') # layout with default (neato)
        G.draw(filename) # draw file
        # G.write('test.dot') # useful for debugging
        print('Drew Graph')
