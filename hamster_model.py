from dataclasses import dataclass
from typing import Optional
from hamster_states import HamsterState, ReactionType

class HamsterModel:
    # initial pos + sz
    x: float = 300.0
    y: float = 200.0
    user_scale: float = 1.0 # initial size :>

    # initial state
    state: HamsterState = HamsterState.IDLE
    state_started_at: float = 0.0  # seconds (time.time())

    # cnt no of pokes
    poke_count: int = 0
    last_poke_at: float = 0.0  # seconds

    # poke once
    reaction: Optional[ReactionType] = None # Optional[] is like if ReactionType is not triggered yet, then reaction = None
    #bubble_text: str = "" # might draw the bubble txt instead
    bubble_until: float = 0.0  # time.time() + số giây mình muốn nó hiện

    # poke a lottt
    pancake_t: float = 0.0  # not squashed yet, fully squashed is 1.0
                            # will go thru 0.1, 0.2 till 1.0 instead of squashed immediately (looks weird gang)




# main stuff: Cur pos + Cur state