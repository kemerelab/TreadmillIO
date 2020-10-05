import time
from typing import Tuple, Union
import numpy

def inside(zone: Tuple[int,int], pos: int) -> bool:
    if (zone[1] > zone[0]): # take into account the fact that the track is circular
        return (pos >= zone[0]) and (pos <= zone[1])
    else:
        return (pos <= zone[1]) or (pos >= zone[0])


    raise(NotImplementedError("Reward types other than classical are not yet implemented"))

class RewardZoneController():
    def __init__(self, params, gpio_interface, sound_controller=None):
        self.Zones = {}

        for reward_name, reward in params['RewardZoneList'].items():
            if reward['Type'] not in ['Classical','Operant']:
                raise(NotImplementedError("Reward types other than classical or operant are not yet implemented"))

            # visualization.add_zone_position(reward['RewardZoneStart'], reward['RewardZoneEnd'], 
            #                 fillcolor=None, edgecolor=reward['Color'], hatch='....', width=1.33, alpha=1.0)

            if (reward['Type'] == 'Classical'):
                self.Zones[reward_name] = ClassicalRewardZone(reward, gpio_interface, sound_controller)
            elif (reward['Type'] == 'Operant'):
                self.Zones[reward_name] = OperantRewardZone(reward, gpio_interface, sound_controller)

    def update_reward_zones(self, time, pos, gpio):
        for _, reward in self.Zones.items():
            if reward.Type == 'Classical':
                reward.update(time, pos)
            elif reward.Type == 'Operant':
                reward.update(time, pos, gpio)


class ClassicalRewardZone():
    def __init__(self, params, gpio_interface, sound_controller=None):

        if (params['DispensePin'] not in gpio_interface.GPIOs) or (gpio_interface.GPIOs[params['DispensePin']]['Type'] != 'Output'):
            raise(ValueError("RewardZone DispensePin not specified as a GPIO output."))
        else:
            self.pin = params['DispensePin']
            self.io_interface = gpio_interface

        self.reward_sound = None
        if ('RewardSound' in params):
            if not sound_controller:
                raise(ValueError("RewardZone RewardSounds require calling class with sound_controller."))
            if sound_controller and (params['RewardSound'] in sound_controller.Beeps):
                self.reward_sound = params['RewardSound']
                self.sound_controller = sound_controller

        self.Type = 'Classical'

        self.active_zone = (params['RewardZoneStart'], params['RewardZoneEnd'])
        if (('ResetZoneStart' in params) and not ('ResetZoneEnd' in params)) or \
           (not ('ResetZoneStart' in params) and ('ResetZoneEnd' in params)):
           raise(ValueError("Both 'ResetZoneStart' and 'ResetZoneEnd' must be specified."))
         
        if ('ResetZoneStart' in params) and ('ResetZoneEnd' in params):
            self.reset_zone = (params['ResetZoneStart'], params['ResetZoneEnd'])
        
        self.refractory_period = params.get('LickTimeout', 0) # by default, classical conditioning has no refractory period
        self.max_rewards = params.get('MaxSequentialRewards', 1) # by default, we should only have one reward
            
        self.pulse_length = params['PumpRunTime']

        self.current_reward_number = 0
        self.last_reward_time = 0
        self.active = True
        self.random_active = True


    def update(self, time, pos):
        if inside(self.active_zone, pos):
            if time > (self.last_reward_time + self.refractory_period ):
                if (self.current_reward_number < self.max_rewards):
                    self.last_reward_time = time
                    self.current_reward_number += 1
                    if (self.current_reward_number >= self.max_rewards):
                        self.active = False

                    self.io_interface.pulse_output(self.pin, time + self.pulse_length) # Trigger GPIO pulse
                    
                    if self.reward_sound and self.sound_controller:
                        self.sound_controller.Beeps[self.reward_sound].play(time) # Play Reward sound

        elif self.reset_zone:
            if inside(self.reset_zone, pos) and not self.active:
                self.current_reward_number = 0
                self.active = True




class OperantRewardZone(ClassicalRewardZone):
    def __init__(self, params, gpio_interface, sound_controller=None):
        ClassicalRewardZone.__init__(self, params, gpio_interface, sound_controller)
        
        if params['LickPin'] not in gpio_interface.GPIOs:
                raise ValueError('Lick pin not in defined GPIO list')
        else:
            self.lick_pin = gpio_interface.GPIOs[params['LickPin']]['Number'] # We are going to bit mask raw GPIO for this

        self.random_assist = None
        if ('RandomAssist' in params):
            if not ( (params['RandomAssist'] >= 0.0) and (params['RandomAssist'] <= 1.0) ):
                raise ValueError('RandomAssist Parameter of Operant Reward zone must be between 0.0 and 1.0!')
            self.random_assist = params['RandomAssist']


        self.Type = 'Operant'

    def update(self, time, pos, gpio, logger=None):
        if inside(self.active_zone, pos):
            if time > (self.last_reward_time + self.refractory_period ):
                if (self.current_reward_number < self.max_rewards): 
                    do_random_reward = False
                    if self.random_assist and self.random_active:
                        self.random_active = False # NOTE: This will make it impossible for multiple free rewards to be delivered in a zone regardless of max_rewards parameter
                        r = numpy.random.rand()
                        if (r < self.random_assist):
                            do_random_reward = True

                    mouse_licked = ((gpio & (0x01 << (self.lick_pin-1))) > 0)
                    if mouse_licked or (do_random_reward):
                        self.last_reward_time = time
                        self.current_reward_number += 1
                        if (self.current_reward_number >= self.max_rewards):
                            self.active = False
			
                        self.io_interface.pulse_output(self.pin, time + self.pulse_length) # Trigger GPIO pulse
                        
                        if self.reward_sound and self.sound_controller:
                            self.sound_controller.Beeps[self.reward_sound].play(time) # Play Reward sound

                        if logger:
                            logger([time, mouse_licked, do_random_reward, pos, gpio]) # Log the reward event if logging


        elif self.reset_zone:
            if inside(self.reset_zone, pos):
                self.random_active = True
                if not self.active:
                    self.current_reward_number = 0
                    self.active = True





    
