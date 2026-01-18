import random
import time

from hamster_states import HamsterState, ReactionType
from hamster_model import HamsterModel

# global constants, needa experiment and change later
COMBO_TIMEOUT_S = 0.20      # how long to wait for a second poke. If after 0.5s dun hv a 2nd poke, then it's a single poke
BUBBLE_DURATION_S = 1.60    # speech bubble lifetime [If we draw in the bubble, then this variable is js to keep track of when hamster return to IDLE]
PANCAKE_IN_S = 1.0         # seconds to squash to full pancake
PANCAKE_HOLD_S = 2.0       # seconds to stay pancaked before recovering


# this kinda like a procedure (mutates the model data, but dun return anything)
def enter_state(ham: HamsterModel, new_state: HamsterState, now: float | None = None) -> None: 
    #           ham = cur data     new_state = state to be switched to     
    """Centralized state transition."""

    if now is None:
        now = time.time()

    ham.state = new_state # change da state
    ham.state_started_at = now # when the new state start

    if new_state == HamsterState.IDLE:
        ham.reaction = None
        #ham.bubble_text = ""
        ham.bubble_until = 0.0
        ham.pancake_t = 0.0
        ham.poke_count = 0

    elif new_state == HamsterState.SINGLE_REACT:
        # reaction must already be chosen by start_single_react()
        ham.pancake_t = 0.0 # for safety only, ensure he's not squashed :>

    elif new_state == HamsterState.PANCAKE:
        ham.reaction = None
        #ham.bubble_text = ""
        ham.bubble_until = 0.0
        ham.pancake_t = 0.0


def on_poke(ham: HamsterModel, now: float | None = None) -> None:
    """Call this when the user pokes. This one mainly handles multi poke. Single poke is handled by update()."""

    if now is None:
        now = time.time()

    if ham.state == HamsterState.PANCAKE: # if pancaked alr, but user bein funny and still wanna poke
        ham.last_poke_at = now
        return # restart pancake timer

    # cnt consecutive pokes 
    if now - ham.last_poke_at <= COMBO_TIMEOUT_S:
        ham.poke_count += 1
    else:
        ham.poke_count = 1

    ham.last_poke_at = now

    # If >= 2 pokes => squash him immediately
    if ham.poke_count >= 2:
        enter_state(ham, HamsterState.PANCAKE, now = now) # STATE TRANSITION 
        return


# randomize between the two possible reaction faces :>
def start_single_react(ham: HamsterModel, now: float) -> None: 
    """Internal: start the 1-poke reaction after combo window passes."""

    ham.reaction = random.choice([ReactionType.ANGRY, ReactionType.SUSPICIOUS])

    #if ham.reaction == ReactionType.ANGRY:
        #ham.bubble_text = "Heyyy, that hurts 😾"
    #else:
        #ham.bubble_text = "Did I just sense someone slacking… 🤨"

    ham.bubble_until = now + BUBBLE_DURATION_S
    enter_state(ham, HamsterState.SINGLE_REACT, now = now) # STATE TRANSITION


def update(ham: HamsterModel, dt: float, now: float | None = None) -> None:
    #                         dt = seconds since last update.
    """ Call this regularly (e.g., every frame). """
    
    if now is None:
        now = time.time()

    if ham.state in (HamsterState.IDLE, HamsterState.SINGLE_REACT):
        # If we saw exactly 1 poke and enough time has passed with no 2nd poke:
        if ham.poke_count == 1 and (now - ham.last_poke_at) > COMBO_TIMEOUT_S:
            start_single_react(ham, now)
            ham.poke_count = 0  # reset poke

    if ham.state == HamsterState.IDLE:
        return

    if ham.state == HamsterState.SINGLE_REACT:
        # hide bubble and return to idle
        if now >= ham.bubble_until:
            enter_state(ham, HamsterState.IDLE, now = now)
        return

    if ham.state == HamsterState.PANCAKE:
        # squash-in phase
        if PANCAKE_IN_S > 0:
            ham.pancake_t = min(1.0, ham.pancake_t + dt / PANCAKE_IN_S)
        else:
            ham.pancake_t = 1.0

        # hold then recover
        if (now - ham.state_started_at) >= (PANCAKE_IN_S + PANCAKE_HOLD_S):
            enter_state(ham, HamsterState.IDLE, now=now)
        return
