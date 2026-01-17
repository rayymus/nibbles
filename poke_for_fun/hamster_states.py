from enum import Enum, auto

class HamsterState(Enum): # depends on the number of pokes
    IDLE = auto() # normal state
    SINGLE_REACT = auto() # if poke once
    PANCAKE = auto() # else :>


class ReactionType(Enum): # this one for poke once
    ANGRY = auto()
    SUSPICIOUS = auto()