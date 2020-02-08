import time
from typing import Tuple, Union

def inside(zone: Tuple[int,int], pos: int) -> bool:
    if (zone[1] > zone[0]): # take into account the fact that the track is circular
        return (pos >= zone[0]) and (pos <= zone[1])
    else:
        return (pos <= zone[1]) or (pos >= zone[0])


class ClassicalRewardZone():
    def __init__(self, activeZone: Tuple[int,int], dispensePin: int, pulseLength:int , rewardSound: str = None,
                        refractoryPeriod : int = 1000,
                        maximumRewards: int = 1, resetZone: Union[None, Tuple[int,int]] = None):

        self.dispensePin = dispensePin
        self.pulseLength = pulseLength
        self.activeZone = activeZone
        self.resetZone = resetZone
        self.refractoryPeriod = refractoryPeriod
        self.maximumRewards = maximumRewards

        self.currentNumberOfRewards = 0
        self.lastRewardTime = 0
        self.active = True

        if rewardSound == 'None':
            self,rewardSound = None
        else:
            self.rewardSound = rewardSound



    def pos_reward(self, pos: int, gpio:int, currentTime: int) -> Union[None, Tuple[int,int]]:
        if inside(self.activeZone, pos):
            if (currentTime > (self.lastRewardTime + self.refractoryPeriod)):
                if (self.currentNumberOfRewards < self.maximumRewards):
                    self.lastRewardTime = currentTime
                    self.currentNumberOfRewards += 1
                    if (self.currentNumberOfRewards >= self.maximumRewards):
                        self.active = False

                    return (self.dispensePin, self.pulseLength, self.rewardSound)

        elif self.resetZone:
            if inside(self.resetZone, pos):
                self.active = True

        return None


class OperantRewardZone():
    def __init__(self, activeZone: Tuple[int,int], lickPin:int, dispensePin: int, pulseLength:int , rewardSound: str = None,
                        refractoryPeriod : int = 1000,
                        maximumRewards: int = 1, resetZone: Union[None, Tuple[int,int]] = None):

        self.dispensePin = dispensePin
        self.pulseLength = pulseLength
        self.activeZone = activeZone
        self.resetZone = resetZone
        self.refractoryPeriod = refractoryPeriod
        self.maximumRewards = maximumRewards

        self.currentNumberOfRewards = 0
        self.lastRewardTime = 0
        self.active = True

        self.lickPin = lickPin

        if rewardSound == 'None':
            self,rewardSound = None
        else:
            self.rewardSound = rewardSound


    def pos_reward(self, pos: int, gpio:int, currentTime: int) -> Union[None, Tuple[int,int]]:
        if inside(self.activeZone, pos):
            if (currentTime > (self.lastRewardTime + self.refractoryPeriod)):
                if (self.currentNumberOfRewards < self.maximumRewards) and ((gpio & (0x01 << (self.lickPin-1))) > 0):
                    self.lastRewardTime = currentTime
                    self.currentNumberOfRewards += 1
                    if (self.currentNumberOfRewards >= self.maximumRewards):
                        self.active = False

                    return (self.dispensePin, self.pulseLength, self.rewardSound)


        elif self.resetZone:
            if inside(self.resetZone, pos):
                self.active = True

        return None



    