import time
import numpy as np
from itertools import cycle
import warnings
import zmq
import random
import pickle
import operator

class StateTransitionCondition:
    def __init__(self, label, state_config, io_interface):
        self.label = label

    def condition(self, io_interface):
        # test if the condtion defined by this object is current true or false
        pass

def get_operator(direction):
    if direction == '>':
        return operator.gt
    elif direction == '>=':
        return operator.ge
    elif direction == '<':
        return operator.lt
    elif direction == '<=':
        return operator.le
    else:
        raise(ValueError("Trying to interpret a conditional transition, but direction {} is not supported").format(direction))


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

        #print(state_config)

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
                    elif params['ConditionType'] == 'Delay':
                        label = 'Delay ({} to {})'.format(self.label, state_name)
                        config = {'Params': params, 'NextState': 'Default'}
                        self.next_state[state_name]['State'] = DelayState(label, config, self.io_interface)
                    elif params['ConditionType'] == 'GPIO':
                        self.next_state[state_name]['Pin'] = params['Pin'] # this will error if its not specified
                        self.next_state[state_name]['Value'] = params['Value'] # this will error if its not specified
                    elif params['ConditionType'] == 'Speed':
                        self.next_state[state_name]['Threshold'] = params['Threshold']
                        self.next_state[state_name]['Direction'] = params['Direction']
                        self.next_state[state_name]['Operator'] = get_operator(params['Direction'])
                    elif params['ConditionType'] == 'Position':
                        self.next_state[state_name]['Threshold'] = params['Threshold']
                        self.next_state[state_name]['Direction'] = params['Direction']
                        self.next_state[state_name]['Operator'] = get_operator(params['Direction'])
                    elif params['ConditionType'] == 'Random':
                        self.next_state[state_name]['RandomPriority'] = params.get('RandomPriority', 1.0)
                    elif params['ConditionType'] == 'None':
                        self.next_state[state_name]['ConditionType'] = 'None'
                    else:
                        self.add_state_transition(state_name, params) # throw error if not implemented for condition
                else:
                    self.next_state[state_name]['ConditionType'] = 'None'


            # Error check priorities
            priorities = [s['Priority'] for (n,s) in self.next_state.items()]
            if len(priorities) > len(set(priorities)):
                raise(ValueError('Non unique state transition priorities detected for state {}.'.format(label)))

        else:
            raise(ValueError('Parsing state machine. State {} needs a next state.'.format(label)))

        # Launch viewer when current state?
        self.render_viewer = state_config.get('Viewer', False)
        self._p_viewer = None

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
                    elif condition['ConditionType'] == 'Delay':
                        next_state.append(  (state_name, 'Delay ({})'.format(condition['State'].label)) )
                    elif condition['ConditionType'] == 'GPIO':
                        next_state.append( (state_name, 'GPIO {} = {}'.format(condition['Pin'], condition['Value'])))
                    elif condition['ConditionType'] == 'Speed':
                        next_state.append( (state_name, 'Speed {} {}'.format(condition['Direction'], condition['Threshold'])))
                    elif condition['ConditionType'] == 'Position':
                        next_state.append( (state_name, 'Position {} {}'.format(condition['Direction'], condition['Threshold'])))
                    else:
                        next_state.append( (state_name, condition['ConditionType']) )
                return next_state
            else:
                return self.next_state

        if isinstance(self.next_state, dict):
            time = self.io_interface.MasterTime
            next_state = []
            priority = []
            for state_name, condition in self.next_state.items():
                if  ((condition['ConditionType'] == 'ElapsedTime') and (time > condition['TransitionTime'])) or \
                    ((condition['ConditionType'] == 'Delay') and (condition['State'].get_next_state())) or \
                    ((condition['ConditionType'] == 'GPIO') and \
                        (self.io_interface.read_pin(condition['Pin']) == condition['Value'])) or \
                    ((condition['ConditionType'] == 'Speed') and \
                        condition['Operator'](self.io_interface.velocity, condition['Threshold'])) or \
                    ((condition['ConditionType'] == 'Position') and \
                        condition['Operator'](self.io_interface.pos, condition['Threshold'])):
                    # (note that we don't even check for "None")
                    next_state.append(state_name)
                    priority.append(condition['Priority'])
                elif condition['ConditionType'] == 'Random': # enable random state transitions using priority
                    next_state.append(state_name)
                    priority.append(np.random.rand() * condition['RandomPriority'])
                elif condition['ConditionType'] == 'None': # add state transition if unconditional
                    next_state.append(state_name)
                    priority.append(condition['Priority'])
                elif condition['ConditionType'] not in ['None', 'ElapsedTime', 'Delay', 'GPIO', 'Speed', 'Position']:
                    if self.check_state_transition(state_name, condition): # check custom state transition
                        next_state.append(state_name)
                        priority.append(condition['Priority'])
            if next_state:
                return( next_state[np.argmax(priority)] ) # return state with the highest priority
            else:
                return( None ) # if no condiditonal condition was matched, we stay in the same state (ignore the sel)
        else:
            return self.next_state

    def on_entrance(self, logger=None):
        if self.render_viewer and self._p_viewer is None:
            from .viewer import launch_viewer
            self._viewer_conn, self._p_viewer = launch_viewer(self.Type)

        if isinstance(self.next_state, dict):
            for state_name, condition in self.next_state.items():
                if (condition['ConditionType'] == 'ElapsedTime'):
                    self.next_state[state_name]['TransitionTime'] = condition['Duration'] + self.io_interface.MasterTime
                    #break # there's only supposed to be one TransitionTime state transition, so we can break if we find it
                elif (condition['ConditionType'] == 'Delay'):
                    self.next_state[state_name]['State'].on_entrance(logger=logger)
        else:
            pass

    def on_exit(self, logger=None):
        pass

    def on_remain(self, logger=None):
        pass

    def add_state_transition(self, state_name, params):
        """Add task-specific state transition."""
        raise NotImplementedError('Parsing state {}. ConditionType {} is not implemented.'
                                  .format(self.label, params['ConditionType']))

    def check_state_transition(self, state_name, params):
        """Check task-specific state transition. Returns True if condition met."""
        raise NotImplementedError('Parsing state {}. ConditionType {} is not implemented.'
                                  .format(self.label, params['ConditionType']))

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

        elif (Params['Duration'] == 'Uniform'):
            self.delay_min = Params['Min']
            self.delay_max = Params['Max']

            delays = np.random.uniform(self.delay_min, self.delay_max, size=(50,))
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
        elif self.delay_type == 'Uniform':
            return label + '<tr><td>Uniform Delay: <br/>' \
                '&#955;= min: {} ms, max: {} ms </td></tr></table>'.format(
                        self.delay_min, self.delay_max)
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

        # return command

    def on_entrance(self, socket, logger= None):
        TaskState.on_entrance(self, logger)
        if self.visType == 'Fixed':
            command = self.command
        elif self.visType == 'Random':
            command = self.command[next(self.CommandIndices)]
        socket.send_string(command)

        time = self.io_interface.MasterTime
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

        time = self.io_interface.MasterTime
        if logger:
            logger([time,-1,-1,-1,-1,'SetGPIO', self.pin, self.level])

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        label += '<tr><td>Set \"{}\"[{}] to {} </td></tr>'.format(self.pin, 
            self.io_interface.GPIOs[self.pin]["Number"],self.level)
        label +='</table>'
        return label


class SetPosition(TaskState):
    def __init__(self, label, state_config, io_interface):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'SetPosition'
        params = state_config['Params']
        self.pos = params['Position']

    def on_entrance(self, logger=None):
        TaskState.on_entrance(self, logger)
        self.io_interface.pos = self.pos

        time = self.io_interface.MasterTime
        if logger:
            logger([time,-1,-1,-1,-1,'SetPosition', self.pos])


class LockPosition(TaskState):
    def __init__(self, label, state_config, io_interface):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'LockPosition'
        params = state_config['Params']
        self.lock_state = params['LockState']

    def on_entrance(self, logger=None):
        TaskState.on_entrance(self, logger)
        self.io_interface.block_movement = self.lock_state

        time = self.io_interface.MasterTime
        if logger:
            logger([time,-1,-1,-1,-1,'LockPosition', self.lock_state])


class SetSoundStimulusState(TaskState):
    def __init__(self, label, state_config, io_interface, sound_controller):
        TaskState.__init__(self, label, state_config, io_interface)
        self.Type = 'SetSoundState'
        params = state_config['Params']

        self.Sound = {}
        
        if sound_controller:
            self.sound_controller = sound_controller
            for sound, value in params.items():
                self.Sound[sound] = {}
                
                if sound in sound_controller.BackgroundSounds:
                    self.Sound[sound]['Sound'] = sound_controller.BackgroundSounds[sound]
                    self.Sound[sound]['Type'] = 'Background'
                elif sound in sound_controller.BundledSounds:
                    self.Sound[sound]['Sound'] = sound_controller.BundledSounds[sound]
                    self.Sound[sound]['Type'] = 'Bundled'
                else:
                    raise(ValueError('SetSoundStimulusState: "{}" not found in Background or Bundled sounds list.'.format(sound)))
                
                if value not in ['On','Off']:
                    raise(ValueError("SetSoundStimulusState 'Value' must be 'On' or 'Off'"))
                else:
                    self.Sound[sound]['Value'] = value

                if value == 'On':
                    self.Sound[sound]['Gain'] = self.Sound[sound]['Sound'].baseline_gain
                elif value == 'Off':
                    self.Sound[sound]['Gain'] = self.Sound[sound]['Sound'].off_gain
        else:
            self.sound_controller = None
            warnings.warn("SetSoundStimulusState won't produce sound bc sound is not enabled.", RuntimeWarning)
            self.Sound = None

        # Bundled sounds params
        self.Index = 0
        self.IncrementIndex = 0

    def set_gain(self):
        if self.Sound:
            for sound, params in self.Sound.items(): 
                params['Sound'].change_gain(params['Gain'])

    def on_entrance(self, logger=None):
        TaskState.on_entrance(self, logger)
        if self.sound_controller:
            if self.Sound:
                for sound, params in self.Sound.items(): 
                    if params['Type'] == 'Bundled':
                        self.Index += self.IncrementIndex
                        params['Sound'].choose_sound(self.Index)
                        self.IncrementIndex = 0
                    params['Sound'].change_gain(params['Gain'])

                time = self.io_interface.MasterTime
                if logger:
                    # TODO: log which sound and which level!
                    logger([time,-1,-1,-1,-1,'SetSoundState'])

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        for sound, params in self.Sound.items(): 
            if params['Value'] == 'On':
                label += '<tr><td>Play {}</td></tr>'.format(params['Sound'].name)
            if params['Value'] == 'Off':
                label += '<tr><td>Stop {}</td></tr>'.format(params['Sound'].name)
        label +='</table>'
        return label


class SetInternalState(TaskState):

    def __init__(self, label, state_config, io_interface, state_dict):
        TaskState.__init__(self, label, state_config, io_interface)

        # Settings
        self.Type = 'SetInternalState'
        params = state_config['Params']

        # Avoid setting mod state here in case 
        # state_dict not yet fully initialized
        self.StateDict = state_dict #  maps name to object
        req_params = ['State', 'InternalState', 'Value']
        if all([k in params for k in req_params]):
            self.ModName = params['State'] # state name
            self.ModState = None # state object
            self.ModAttribute = params['InternalState'] # state attribute
            self.ModValue = params['Value'] # new value
        else:
            raise ValueError(', '.join(req_params) + ' are required parameters.')

    def _set_mod_state(self, name):
        """Finds state object to modify."""
        # Check that mapping exists
        if name in self.StateDict:
            self.ModState = self.StateDict[name]
        else:
            raise ValueError('State \'{}\' not found.'.format(name))
        
        # Check that object has attribute
        if not hasattr(self.ModState, self.ModAttribute):
            raise ValueError('State \'{}\' does not have attribute \'{}\'.'
                             .format(self.ModState, self.ModAttribute))

    def _get_value_from_key(self, key):
        """Returns special cases for values of internal states."""
        if key.lower() == 'currenttime':
            return self.io_interface.MasterTime
        else:
            raise ValueError('Unknown key \'{}\'.'.format(key))

    def _get_value_from_state(self, name, attr):
        """Returns value of attribute from another state"""
        # Check that mapping exists
        if name in self.StateDict:
            state = self.StateDict[name]
        else:
            raise ValueError('State \'{}\' not found.'.format(name))

        # Check for attribute
        if hasattr(state, attr):
            return getattr(state, attr)
        else:
            raise AttributeError('State {} does not have attribute {}.'.format(state, attr))

    def set_internal_state(self, value):
        # Initialize mod state if not already
        if self.ModState is None:
            self._set_mod_state(self.ModName)
        
        # Look up value if needed
        if isinstance(value, str):
            value = self._get_value_from_key(value)
        elif isinstance(value, dict):
            if len(value) > 1:
                raise ValueError('Can only set one value.')
            value = self._get_value_from_state(*[(k, v) for k, v in value.items()][0])
        
        setattr(self.ModState, self.ModAttribute, value)

    def on_entrance(self, logger=None):
        TaskState.on_entrance(self, logger)
        self.set_internal_state(self.ModValue)

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        label += '<tr><td align="left">State: {}</td></tr>'.format(self.ModName)
        label += '<tr><td align="left">Internal State: {}</td></tr>'.format(self.ModAttribute)
        label += '<tr><td align="left">Value: {}</td></tr>'.format(self.ModValue)
        label +='</table>'
        return label


class PatchState(TaskState):

    def __init__(self, label, state_config, io_interface):
        # Default parameters prior to superclass init
        self._has_reward_state = False
        self._increment_size = np.inf

        # Superclass init
        TaskState.__init__(self, label, state_config, io_interface)

        # Settings
        self.Type = 'PatchState'
        self.NewPatch = True # reset patch on entrance
        self.RewardHarvest = 0.0 # reward harvested in time step
        self.R_harvest = 0.0 # total harvested reward in current patch
        self.increments = 0 # number of increments corresponding to reward tone steps
        params = state_config['Params']

        # Parse parameters
        if 'ModelType' not in params:
            raise ValueError('Model type is a required parameter.')
        elif params['ModelType'] == 'Exponential':
            self.Model = ExponentialPatch(params['ModelType'], 
                                          params['ModelParams'],
                                          params.get('SwitchRate', 0.0),
                                          self.io_interface.MasterTime)
        elif params['ModelType'] == 'Poisson':
            self.Model = PoissonPatch(params['ModelType'], 
                                      params['ModelParams'],
                                      params.get('SwitchRate', 0.0),
                                      self.io_interface.MasterTime)
        else:
            raise NotImplementedError('Model type \'{}\' has not been implemented.'
                                      .format(params['ModelType']))

        # Check required reward state
        if not self._has_reward_state:
            raise SyntaxError('State transition of Reward type is required for PatchState.')

        # Initialize tracking variables
        self._prev_available_reward = self.available_reward

    def add_state_transition(self, state_name, params):
        if params['ConditionType'] == 'Reward':
            #self.next_state[state_name]['ConditionType'] = 'Reward' # added in TaskState
            self.next_state[state_name]['Value'] = params['Value']
            self._has_reward_state = True
        elif params['ConditionType'] == 'Increment':
            self.next_state[state_name]['Value'] = params['Value']
            self._increment_size = params['Value']
        elif params['ConditionType'] == 'Decrement':
            self.next_state[state_name]['Value'] = params['Value']
        else:
            raise NotImplementedError('Condition type \'{}\' not implemented for PatchState.'
                                      .format(params['ConditionType']))

    def check_state_transition(self, state_name, params):
        if params['ConditionType'] == 'Reward':
            return (self.available_reward >= params['Value'])
        elif params['ConditionType'] == 'Increment':
            return ((self.available_reward // params['Value']) 
                    > (self._prev_available_reward // params['Value']))
        elif params['ConditionType'] == 'Decrement':
            return ((self.available_reward // params['Value']) 
                    < (self._prev_available_reward // params['Value']))
        else:
            raise NotImplementedError('Condition type \'{}\' not implemented for PatchState.'
                                      .format(params['ConditionType']))

    def on_entrance(self, logger=None):
        TaskState.on_entrance(self, logger)

        # Cache previous reward
        self._prev_available_reward = self.available_reward

        # Add reward if harvested
        if self.RewardHarvest > 0.0:
            self.R_harvest += self.RewardHarvest
            self.RewardHarvest = 0.0

        if self.NewPatch:
            # Reset patch model if entering new patch
            self.reset()
            if self.render_viewer:
                update_dict = {'reset': None, 'priority': 1}
                self._viewer_conn.send_bytes(pickle.dumps(update_dict))
        else:
            # Update patch statistics, i.e. if reward is available
            self.update()
            if self.render_viewer:
                update_dict = {'reward': [self.Model.t, self.available_reward],
                               'priority': 1} # don't skip first data point
                self._viewer_conn.send_bytes(pickle.dumps(update_dict))

    def on_remain(self, logger=None):
        # Update patch statistics, i.e. if reward is available
        self.update()
        if self.render_viewer:
            update_dict = {'reward': [self.Model.t, self.available_reward],
                           'priority': 0} # can skip intermediate data points
            self._viewer_conn.send_bytes(pickle.dumps(update_dict))

    def reset(self):
        self.Model.reset(self.io_interface.MasterTime)
        self.NewPatch = False
        self.R_harvest = 0.0
        self.increments = 0

    def update(self):
        # Update model
        self.Model.update(self.io_interface.MasterTime)

        # Update increments
        self.increments = int(self.available_reward // self._increment_size)

    @property
    def available_reward(self):
        return self.Model.R - self.R_harvest

    @property
    def ToneIndex(self):
        return self.increments - 1

    def get_graph_label(self):
        label = '<table border="0"><tr><td>{}</td></tr>'.format(TaskState.get_graph_label(self))
        label += '<tr><td align="left">Model Type: {}</td></tr>'.format(self.Type)
        label += '<tr><td align="left">Model Params: </td></tr>'
        for name, p in self.Model.param_config.items():
            if isinstance(p, dict):
                p = ', '.join(['{}={}'.format(k, v) for k, v in p.items()])
            label += '<tr><td align="left">&emsp;{}: {}</td></tr>'.format(name, p)
        label +='</table>'
        return label



class PatchModel():

    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = []

    def __init__(self, patch_type, params, p_switch=0.0, init_time=0.0, time_base='millis'):
        # Settings
        self.Type = patch_type

        # Set internal state
        self.R = 0 # current total reward
        self.t = init_time # current time (sec)
        self.t0 = init_time # initial time at start (sec)
        if time_base == 'millis':
            self._base = 1.0e-3
        elif time_base == 'seconds':
            self._base = 1.0

        # New patch probability
        self.p_switch = p_switch

        # Placeholder for parameters
        self._check_params(list(params.keys()))
        self.param_config = params
        self.params = {}
        self.set_params()

    def _check_params(self, param_names):
        req_params = {k: False for k in param_names}
        for name in param_names:
            if name not in self.REQUIRED_PARAMS and name not in self.OPTIONAL_PARAMS:
                raise ValueError('Model does not have parameter \'\'.'.format(name))
            elif name in self.REQUIRED_PARAMS:
                req_params[name] = True

        if not all([v for k, v in req_params.items()]):
            raise ValueError('Model requires parameters {}'
                             .format(', '.join(self.REQUIRED_PARAMS)))

    def get_params(self, config):
        if not isinstance(config, dict):
            return config
        elif 'Distribution' not in config:
            raise ValueError('Parameter configuration must specify distribution.')
        if config['Distribution'] == 'Uniform':
            return np.random.uniform(config['Low'], config['High'])
        elif config['Distribution'] == 'LogUniform':
            if config['Low'] <= 0.0:
                raise ValueError('Bounds must be positive numbers.')
            return np.exp(np.random.uniform(np.log(config['Low']), np.log(config['High'])))
        else:
            raise NotImplementedError('Distribution \'{}\' has not been implemented.'
                                      .format(config['Distribution']))

    def set_params(self):
        for name, value in self.param_config.items():
            self.params[name] = self.get_params(value)

    def update(self, time):
        # Subclasses should use self.t instead of time in order to
        # avoid potential conversion errors
        self.t = time*self._base - self.t0 # convert to seconds

    def reset(self, time=0.0):
        self.R = 0.0
        self.t = 0.0
        self.t0 = time*self._base # convert to seconds

        if random.random() < self.p_switch:
            self.set_params()

class ExponentialPatch(PatchModel):

    REQUIRED_PARAMS = ['tau', 'r0']

    def __init__(self, patch_type, params, p_switch=0.0, init_time=0.0, time_base='millis'):
        """
        Creates patch that fills by exponentially-decaying reward rate.

        Required parameters:
        - tau: reward decay rate (sec)
        - r0: initial reward rate (uL/s)
        """
        PatchModel.__init__(self, patch_type, params, p_switch, init_time, time_base)

        # Follows exponential decay:
        # r(t) = r0 * e^(-t/tau)

        # We could instead determine reward times now to save computation, 
        # but that would require knowing the Reward state transition threshold
        # in the initialization. Not sure which way is better...
        #n = np.arange(int(tau*r0/R0)) # total number of rewards
        #t_reward = -tau*np.log(1.0 - (n*R0)/(tau*r0)) * 1000 # ms
        #self.t_reward = np.append(t_reward, np.inf) # reward times (ms)
        #self.n_reward = 0 # current reward number

    @property
    def _r0(self):
        return self.params['r0']

    @property
    def _tau(self):
        return self.params['tau']

    def r_func(self, t):
        return self._r0*np.exp(-t/self._tau)

    def R_func(self, t):
        return self._r0*self._tau*(1.0 - np.exp(-t/self._tau))

    def update(self, time):
        PatchModel.update(self, time)
        self.R = self.R_func(self.t)
 
class PoissonPatch(PatchModel):
    
    REQUIRED_PARAMS = ['tau', 'V0', 'lambda0']

    def __init__(self, patch_type, params, p_switch=0.0, init_time=0.0, time_base='millis'):
        """
        Creates patch that fills by drips following Poisson process.

        Required parameters:
        - tau: decay rate for Poisson rate parameter lambda (sec)
        - V0: drip size (uL)
        - lambda0: initial Poisson rate parameter (sec)
        """
        PatchModel.__init__(self, patch_type, params, p_switch, init_time, time_base)

        # Placeholder for drip times
        self.t_drip = None

    @property
    def _tau(self):
        return self.params['tau']

    @property
    def _V0(self):
        return self.params['V0']

    @property
    def _lambda0(self):
        return self.params['lambda0']

    def _lam(self, t):
        return self._lambda0*np.exp(-t/self._tau)

    def _Lam(self, t, s):
        return self._lambda0*self._tau*(np.exp(-t/self._tau) - np.exp(-(t+s)/self._tau))

    def _inv_cdf(self, F, t_0):
        return -(1.0/self._lam(t_0))*np.log(1.0 - F)

    def _interevent_times(self, n, t, t_max=1000.0):
        # Generate interevent times for lam(t)
        F = np.random.uniform(size=n)
        t = self._inv_cdf(F, t)
        t[t > t_max] = t_max # cutoff at maximum interval
        return t

    def _events(self, t, s, t_max=1000.0):
        """Generate number of events based on instantaneous Poisson rate."""
        # Guess number of events as Poisson mean
        mean = self._lam(t)*s
        chunk = max(int(mean), 1)
        
        # Generate interevent times
        t = self._interevent_times(chunk, t, t_max)
        T = np.cumsum(t) # event times
        idx = np.searchsorted(T, s, side='left')
        n = idx  # number of event times < s

        # Continue sampling time until time s reached
        while (idx == T.size):
            t = self._interevent_times(chunk, t, t_max)
            T = np.cumsum(t) + T[-1]
            idx = np.searchsorted(T, s, side='left')
            n += idx
            
        return n

    def _create_drip_times(self, t, s, t_max=None):
        if t_max is None:
            t_max = s

        # Get event times with rate lambda_max
        lam_max = self._lam(t) # current rate is maximum due to exponential decay
        N_s = self._events(t, s, t_max) # number of events
        #N_s = np.random.poisson(lam_max*s)
        t_event = np.sort(np.random.uniform(low=t, high=t+s, size=N_s)) # time of events
        
        # Prune drip times to generate inhomogeneous process
        lam_t = self._lam(t_event)
        U = np.random.uniform(size=N_s)
        return t_event[U <= (lam_t / lam_max)]

    def update(self, time):
        PatchModel.update(self, time)

        if self.t_drip is None:
            self.t_drip = self._create_drip_times(self.t, 1000.0)

        self.R = np.sum(self.t_drip <= self.t)*self._V0

    def reset(self, time=0.0, **params):
        PatchModel.reset(self, time)

        self.t_drip = None


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
        set_internal = {} # SetInternalStates must be processed last
        for state_name, state in config['States'].items():
            if 'FirstState' in state and state['FirstState']:
                self.FirstState = state_name

            if (state['Type'] == 'Base'):
                self.StateMachineDict[state_name] = TaskState(
                    state_name, state, io_interface)

            elif (state['Type'] == 'Delay'):
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

            elif (state['Type'] == 'SetPosition'):
                self.StateMachineDict[state_name] = SetPosition(
                    state_name, state, io_interface)

            elif (state['Type'] == 'LockPosition'):
                self.StateMachineDict[state_name] = LockPosition(
                    state_name, state, io_interface)

            elif (state['Type'] == 'Patch'):
                self.StateMachineDict[state_name] = PatchState(
                    state_name, state, io_interface)

            elif (state['Type'] == 'SetInternalState'):
                set_internal[state_name] = state

            else:
                raise(NotImplementedError("Unknown state machine element {}".format(state['Type'])))

        for state_name, state in set_internal.items(): # avoids KeyError if state not yet added
            # NOTE: Is it better to parse State parameter here, 
            #       or to pass entire dict to SetInternalState object?
            self.StateMachineDict[state_name] = SetInternalState(
                state_name, state, io_interface, self.StateMachineDict)
            
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

        self.render_viewer = config.get('Viewer', False)
        if self.render_viewer:
            from .viewer import launch_viewer
            self._viewer_conn, self._p_viewer = launch_viewer('StateMachine', self.render())

    def __enter__(self):
        if self.needs_zmq:
            self.socket = self.zmq_context.socket(zmq.PAIR)
            self.socket.connect("tcp://localhost:%s" % self.port)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        print('TaskStateMachine: exiting because of exception <{}>'.format(exc_type.__name__))
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
            # print(self.CurrentState.label) # TODO: Add Degug/Verbosity to the configuration and spit these out if it's set
            if isinstance(self.CurrentState, VisualizationState):
                self.CurrentState.on_entrance(self.socket, logger)
            else:
                self.CurrentState.on_entrance(logger)

            if self.render_viewer:
                update_dict = {self.CurrentState.label: None, 'priority': 0}
                self._viewer_conn.send_bytes(pickle.dumps(update_dict))
        else:
            self.CurrentState.on_remain(logger)

        next_state = self.CurrentState.get_next_state()
        if next_state is not None:
            self.CurrentState.on_exit(logger)
            self.CurrentState = self.StateMachineDict[next_state]
            self.new_state = True
        else:
            self.new_state = False


    def render(self, filename=None):
        import pygraphviz

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
        if filename is not None:
            G.draw(filename) # draw file
            # G.write('test.dot') # useful for debugging
            print('Drew Graph')
        return G
