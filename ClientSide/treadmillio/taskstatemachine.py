import time
import numpy as np
from itertools import cycle
import warnings
import zmq

import pygraphviz

class StateTransitionCondition:
    def __init__(self, label, state_config, io_interface):
        self.label = label

    def condition(self, io_interface):
        # test if the condtion defined by this object is current true or false
        pass

class TaskState:
    def __init__(self, label, state_config, io_interface):
        self.Type = None
        self.label = label

        print(state_config)

        self.next_state = state_config['NextState']
        self.io_interface = io_interface

        # if not isinstance(Params['NextState'], list):
        #     Params['NextState']

    def get_graph_label(self):
        return '<font point-size="18">{}: <b>{}</b></font>'.format(self.Type, self.label)

    def get_next_state(self, rendering=False):
        return self.next_state

    def on_entrance(self, logger=None):
        pass

    def on_exit(self, logger=None):
        pass

    def on_remain(self, logger=None):
        pass


class DelayState(TaskState):
    def __init__(self, label, state_config, io_interface):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'Delay'
        Params = state_config['Params']
        self.delay_type = Params['Duration']
        self.delay_end = 0
        self.is_waiting = False

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

    def on_entrance(self, logger=None):
        if not self.is_waiting:
            delay = next(self.DelayList)
            time = self.io_interface.MasterTime
            self.delay_end = time + delay
            self.is_waiting = True
        else:
            pass
    
    def on_exit(self, logger=None):
        self.is_waiting = False
        self.delay_end = 0

    def get_next_state(self, rendering=False):
        if not rendering:
            time = self.io_interface.MasterTime
            if (time > self.delay_end):
                return self.next_state
            else:
                return None
        else:
            return [(self.next_state, 'After delay'),
                    (self.label, '')]

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
    def __init__(self, label, state_config, io_interface):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'Visualization'
        params = state_config['Params']


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

    def on_entrance(self, socket, logger= None):
        if self.visType == 'Fixed':
            command = self.command
        elif self.visType == 'Random':
            command = self.command[next(self.CommandIndices)]
        socket.send_string(command)

        if logger:
            logger([time,-1,-1,-1,-1,'Visualization', command])


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
    def __init__(self, label, state_config, io_interface, sound_controller):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'Reward'
        params = state_config['Params']

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

    def on_entrance(self, logger=None):
        time = self.io_interface.MasterTime
        self.io_interface.pulse_output(self.pin, time + self.duration)
        print('Reward!')
        if self.RewardSound:
            self.RewardSound.play(time)

        if logger:
            logger([time,-1,-1,-1,-1,'Reward', self.pin, self.duration])  

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        label += '<tr><td>Pulse [{}]({}) for {} ms</td></tr>'.format(
            self.pin,self.io_interface.GPIOs[self.pin]['Number'],self.duration)
        if self.RewardSound:
            label += '<tr><td>Play {}</td></tr>'.format(self.RewardSound.filename)
        label +='</table>'
        return label


class SetGPIOState(TaskState):
    def __init__(self, label, state_config, io_interface):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'SetGPIO'
        params = state_config['Params']

        if (params['Pin'] not in io_interface.GPIOs) or (io_interface.GPIOs[params['Pin']]['Type'] != 'Output'):
            raise ValueError('TaskState SetGPIO Pin not specified as a GPIO output.')

        self.pin = params['Pin']
        self.level = params['Value']

    def setGPIO(self):
        if self.level:
            self.io_interface.raise_output(self.pin)
        else:
            self.io_interface.lower_output(self.pin)

        return self.pin, self.level

    def on_entrance(self, logger=None):
        if self.level:
            self.io_interface.raise_output(self.pin)
        else:
            self.io_interface.lower_output(self.pin)

        if logger:
            logger([time,-1,-1,-1,-1,'SetGPIO', self.pin, self.level])

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        label += '<tr><td>Set \"{}\"[{}] to {} </td></tr>'.format(self.pin, 
            self.io_interface.GPIOs[self.pin]["Number"],self.level)
        label +='</table>'
        return label


class SetSoundStimulusState(TaskState):
    def __init__(self, label, state_config, io_interface, sound_controller):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'SetSoundState'
        params = state_config['Params']

        if ('Sound' not in params) or ('Value' not in params):
            raise(ValueError("SetSoundStimulusState needs a 'Sound' and a 'Value'."))

        if  params['Value'] not in ['On','Off']:
            raise(ValueError("SetSoundStimulusState 'Value' must be 'On' or 'Off'"))

        self.Value = params['Value']
        
        if sound_controller:
            self.sound_controller = sound_controller
            if params['Sound'] not in sound_controller.BackgroundSounds:
                    raise(ValueError('SetSoundStimulusState: "{}" not found in Background sounds list.'.format(params['Sound'])))
            self.Sound = sound_controller.BackgroundSounds[params['Sound']]
            if self.Value == 'On':
                self.gain = self.Sound.baseline_gain
            elif self.Value == 'Off':
                self.gain = self.Sound.off_gain
        else:
            self.sound_controller = None
            warnings.warn("SetSoundStimulusState won't produce sound bc sound is not enabled.", RuntimeWarning)
            self.Sound = None

    def set_gain(self):
        if self.Sound:
            self.Sound.change_gain(self.gain)

    def on_entrance(self, logger=None):
        if self.sound_controller:
            if self.Sound:
                self.Sound.change_gain(self.gain)

                if logger:
                    # TODO: log which sound and which level!
                    logger([time,-1,-1,-1,-1,'SetSoundState'])

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
                    state_name, state, io_interface)

            elif (state['Type'] == 'SetGPIO'):
                self.StateMachineDict[state_name] = SetGPIOState(
                    state_name, state, io_interface)

            elif (state['Type'] == 'SetSoundState'):
                self.StateMachineDict[state_name] = SetSoundStimulusState(
                    state_name, state, io_interface, sound_controller)

            elif (state['Type'] == 'Reward'):
                self.StateMachineDict[state_name] = RewardState(
                    state_name, state, io_interface, sound_controller)

            elif (state['Type'] == 'Visualization'):
                self.StateMachineDict[state_name] = VisualizationState(
                    state_name, state, io_interface)
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


    def update_statemachine(self, logger=None):
        time = self.io_interface.MasterTime

        if isinstance(self.CurrentState, VisualizationState):
            self.CurrentState.on_entrance(self.socket, logger)
        else:
            self.CurrentState.on_entrance(logger)

        next_state = self.CurrentState.get_next_state()
        if next_state is not None:
            self.CurrentState.on_exit(logger)
            self.CurrentState = self.StateMachineDict[next_state]
        else:
            self.CurrentState.on_remain(logger)

        # if self.StateMachineWaiting:  # Currently in a `Delay` or other state in which we shouldn't transition yet
        #     if time > self.StateMachineWaitEndTime:
        #         self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]
        #         self.StateMachineWaiting = False
        #     else:
        #         pass
        # else:
        #     if self.CurrentState.Type == 'Delay':
        #         delay = self.CurrentState.getDelay()
        #         self.StateMachineWaitEndTime = time + delay
        #         self.StateMachineWaiting = True
        #         if logger:
        #             logger([time,-1,-1,-1,-1,'Delay', delay])

        #     elif self.CurrentState.Type == 'SetGPIO':
        #         pin, level = self.CurrentState.setGPIO()
        #         if logger:
        #             logger([time,-1,-1,-1,-1,'SetGPIO', pin, level])
        #         self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

        #     elif self.CurrentState.Type == 'SetSoundState':
        #         if self.sound_controller:
        #             self.CurrentState.set_gain()
        #         if logger:
        #             # TODO: log which sound and which level!
        #             logger([time,-1,-1,-1,-1,'SetSoundState'])
        #         self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

        #     elif self.CurrentState.Type == 'Reward':
        #         pin, duration = self.CurrentState.triggerReward(time)
        #         if logger:
        #             logger([time,-1,-1,-1,-1,'Reward', pin, duration])
        #         self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]

        #     elif self.CurrentState.Type == 'Visualization':
        #         command = self.CurrentState.getVisualizationCommand()
        #         self.socket.send_string(command)

        #         if logger:
        #             logger([time,-1,-1,-1,-1,'Visualization', command])
        #         self.CurrentState = self.StateMachineDict[self.CurrentState.NextState]


    def render(self, filename):
        G = pygraphviz.AGraph(directed=True, rankdir='LR', type='UTF-8')
        for state_name, state in self.StateMachineDict.items():
            G.add_node(state.label, label='<'+state.get_graph_label()+'>',shape='box')
        for state_name, state in self.StateMachineDict.items():
            next_state = state.get_next_state(rendering=True)
            if not isinstance(next_state, list):
                next_state = [next_state]

            if isinstance(next_state, list):
                for ns in next_state:
                    if isinstance(ns, tuple):
                        G.add_edge(state.label, self.StateMachineDict[ns[0]].label, label=ns[1])
                    elif ns is not None:
                        G.add_edge(state.label, self.StateMachineDict[ns].label)
        
        G.node_attr.update(fontname='helvetica', fontsize="10")
        G.edge_attr.update(len=3)
        G.layout('neato') # layout with default (neato)
        G.draw(filename) # draw file
        # G.write('test.dot') # useful for debugging
        print('Drew Graph')
