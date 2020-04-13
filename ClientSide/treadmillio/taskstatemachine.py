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
# Example yaml:
#    ExampleState:
#      NextState: 'SomeState'
#    ExampleStateWithConditions:
#      NextState: # NOTE: If no conditions are satisfied, the default is to
#                 #       return to the current state (infinite loop)
#                 # NOTE: Self transitions trigger the on_remain() function
#                 #       rather than the on_entrance() function. And they
#                 #       don't trigger the on_exit() function.
#        SomeDefaultState1: 
#          ConditionType: 'None'
#          Priority: 0 # NOTE: If multiple conditions are satisfied, higher priority
#                      #       transition is taken. By default states are assigned
#                      #       priorities starting at -1 and decreasing. So without
#                      #       assigned probabilities, the first transition is considered
#                      #       the most important.
#        SomeState2:
#          ConditionType: 'ElapsedTime' # transition after a certain amount of time
#                                  # NOTE: You can only have one of these. If you want
#                                  #       an action to be able to reset the timer, use a
#                                  #       transition to a dummy state and then back.
#          Duration: 1000 #ms
#          Priority: 1
#        SomeState3: 
#          ConditionType: 'GPIO' # transition if a GPIO has some value
#          Pin: 'SomePinLabel'
#          Value: True # True or False (boolean == bit)
#          Priority: 2
#        SomeState4: 
#          ConditionType: 'GPIO' # transition based on an equation of GPIO values
#          Equation: 'SomePin1Label AND SomePin2Label OR SomPin3Label' # AND, OR, XOR, NOT allowed
#          Priority: 3

    def __init__(self, label, state_config, io_interface):
        self.Type = None
        self.label = label

        print(state_config)

        #self.next_state = state_config['NextState']
        self.io_interface = io_interface


        if isinstance(state_config['NextState'], str):
            self.next_state = state_config['NextState']
        elif isinstance(state_config['NextState'], dict):
            self.next_state = {}
            priority_counter = -1
            for state_name, params in state_config['NextState'].items():
                self.next_state[state_name] = {}

                if not params:
                    params = {}

                if 'Priority' in params:
                    self.next_state[state_name]['Priority'] = params['Priority']
                else:
                    # Auto-assign conditional transition priority based on order.
                    self.next_state[state_name]['Priority'] = priority_counter
                    priority_counter = priority_counter - 1

                if 'ConditionType' in params:
                    self.next_state[state_name]['ConditionType'] = params['ConditionType']
                    if params['ConditionType'] == 'ElapsedTime':
                        self.next_state[state_name]['Duration'] = params['Duration'] # this will error if its not specified
                        self.next_state[state_name]['TransitionTime'] = -1
                    elif params['ConditionType'] == 'GPIO':
                        self.next_state[state_name]['Pin'] = params['Pin'] # this will error if its not specified
                        self.next_state[state_name]['Value'] = params['Value'] # this will error if its not specified
                    elif params['ConditionType'] == 'None':
                        pass
                    else:
                        raise(ValueError('Parsing state {}. ConditionType {} is not implemented.'.format(label, params['ConditionType'])))
                else:
                    self.next_state[state_name]['ConditionType'] = 'None'


            # Error check priorities
            priorities = [s['Priority'] for (n,s) in self.next_state.items()]
            if len(priorities) > len(set(priorities)):
                raise(ValueError('Non unique state transition priorities detected for state {}.'.format(label)))

        else:
            raise(ValueError('Parsing state machine. State {} needs a next state.'.format(label)))


    def get_graph_label(self):
        return '<font point-size="18">{}: <b>{}</b></font>'.format(self.Type, self.label)

    def get_next_state(self, rendering=False):
        if rendering:
            if isinstance(self.next_state, dict):
                next_state = []
                for state_name, condition in self.next_state.items():
                    if condition['ConditionType'] == 'None':
                        next_state.append( (state_name, 'Default') )
                    elif condition['ConditionType'] == 'ElapsedTime':
                        next_state.append( (state_name, 'Elapsed Time ({} ms)'.format(condition['Duration'])))
                    elif condition['ConditionType'] == 'GPIO':
                        next_state.append( (state_name, 'GPIO {} = {}'.format(condition['Pin'], condition['Value'])))
                return next_state
            else:
                return self.next_state

        if isinstance(self.next_state, dict):
            time = self.io_interface.MasterTime
            next_state = []
            priority = []
            for state_name, condition in self.next_state.items():
                if  ((condition['ConditionType'] == 'ElapsedTime') and (time > condition['TransitionTime'])) or \
                    ((condition['ConditionType'] == 'GPIO') and \
                        (self.io_interface.read_pin(condition['Pin']) == condition['Value'])):
                    # (note that we don't even check for "None")
                    next_state.append(state_name)
                    priority.append(condition['Priority'])
            if next_state:
                return( next_state[np.argmax(priority)] ) # return state with the highest priority
            else:
                return( None ) # if no condiditonal condition was matched, we stay in the same state (ignore the sel)
        else:
            return self.next_state

    def on_entrance(self, logger=None):
        if isinstance(self.next_state, dict):
            for state_name, condition in self.next_state.items():
                if (condition['ConditionType'] == 'ElapsedTime'):
                    self.next_state[state_name]['TransitionTime'] = condition['Duration'] + self.io_interface.MasterTime
                break # there's only supposed to be one TransitionTime state transition, so we can break if we find it
        else:
            pass

    def on_exit(self, logger=None):
        pass

    def on_remain(self, logger=None):
        pass




class DelayState(TaskState):
# Example yaml:
#    ExampleFixedDelayState:
#      Type: 'Delay'
#      Params:
#        Duration: 'Fixed'
#        Value: 1000 # ms
#      NextState: 'ExampleExponentialDelayState'
#    ExampleExponentialDelayState:
#      Type: 'Delay'
#      Params:
#        Duration: 'Exponential'
#        Rate: 1000 # rate of exponential r.v. in ms
#        Min: 2000  # minimum value - this is added to samples drawn from distribution
#        Max: 4000  # maximum value - all values are truncated to this *after adding minimum*
#      NextState: 'Something'

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

    # def getDelay(self):
        # return next(self.DelayList)

    def on_entrance(self, logger=None):
        delay = next(self.DelayList)
        time = self.io_interface.MasterTime
        self.delay_end = time + delay
    
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

    # def getVisualizationCommand(self):
        # if self.visType == 'Fixed':
            # command = self.command
        # elif self.visType == 'Random':
            # command = self.command[next(self.CommandIndices)]

        return command

    def on_entrance(self, socket, logger= None):
        TaskState.on_entrance(self, logger)
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
        TaskState.on_entrance(self, logger)
        time = self.io_interface.MasterTime
        self.io_interface.pulse_output(self.pin, time + self.duration)
        print('Reward! ({})'.format(self.label))
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
        TaskState.on_entrance(self, logger)
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
        TaskState.on_entrance(self, logger)
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
        self.new_state = True

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
        # if (self.CurrentState.Type == 'Delay'):
            # self.StateMachineWaitEndTime = time + self.CurrentState.getDelay()
            # self.StateMachineWaiting = True
        self.new_state = True
        pass


    def update_statemachine(self, logger=None):
        time = self.io_interface.MasterTime

        if self.new_state:
            if isinstance(self.CurrentState, VisualizationState):
                self.CurrentState.on_entrance(self.socket, logger)
            else:
                self.CurrentState.on_entrance(logger)
        else:
            self.CurrentState.on_remain(logger)

        next_state = self.CurrentState.get_next_state()
        if next_state is not None:
            self.CurrentState.on_exit(logger)
            self.CurrentState = self.StateMachineDict[next_state]
            self.new_state = True
        else:
            self.new_state = False


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
