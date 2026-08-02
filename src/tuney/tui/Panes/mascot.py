"""The animated mascot shown above the chat dialog.

Frames come from `mascot_frames`, baked out of `spritesheets/` by
`scripts/bake_mascot.py`. They carry no colour of their own, so the ink takes
the widget's CSS `color` and follows the theme.
"""

from enum import StrEnum
from dataclasses import dataclass

from rich.text import Text
from textual.widgets import Static

from . import mascot_frames


class MascotState(StrEnum):
    """What the agent is doing, as far as the user should be able to tell."""

    IDLE = "idle"
    THINKING = "thinking"           # reasoning, before any answer text
    TALKING = "talking"             # streaming the answer
    WORKING = "working"             # a long, silent tool call is running
    DELEGATING = "delegating"       # a specialist subagent is running
    WAITING = "waiting"             # blocked on the user's confirmation
    DONE = "done"
    ERROR = "error"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class _Spec:
    """How one state animates.

    `frames` names a spritesheet and `fallback` the one to borrow until it has
    been drawn. `loop` states run until something else moves them; the rest
    play `repeat` times, then hand over to `then` or hold their last frame.
    """

    frames: str
    interval: float
    loop: bool = True
    repeat: int = 1
    then: "MascotState | None" = None
    fallback: str = "idle"


# Intervals are seconds per frame.
_SPECS: dict[MascotState, _Spec] = {
    MascotState.IDLE: _Spec("idle", 0.90),
    MascotState.THINKING: _Spec("thinking", 0.45),
    MascotState.TALKING: _Spec("talking", 0.30),
    MascotState.WORKING: _Spec("working", 0.36, fallback="thinking"),
    MascotState.DELEGATING: _Spec("delegating", 0.40, fallback="thinking"),
    MascotState.WAITING: _Spec("waiting", 0.80),
    MascotState.DONE: _Spec("done", 0.32, loop=False, repeat=2,
                            then=MascotState.IDLE),
    MascotState.ERROR: _Spec("error", 0.32, loop=False),
    MascotState.INTERRUPTED: _Spec("interrupted", 0.32, loop=False,
                                   then=MascotState.IDLE),
}

def resting_state(state: MascotState) -> MascotState:
    """Where the mascot ends up once `state` has finished playing — what a
    poll loop should assert, so it doesn't restart a one-shot every tick."""
    return _SPECS[state].then or state


_TINTS = {
    MascotState.WAITING: "-waiting",
    MascotState.DONE: "-done",
    MascotState.ERROR: "-error",
    MascotState.INTERRUPTED: "-error",
}


class Mascot(Static):
    """Plays the frame loop for whichever state it's been put in.

    Its height is pinned to the sprite's, since the chat pane sizes the reply
    panel around it.
    """

    DEFAULT_CSS = f"""
    Mascot {{
        height: {mascot_frames.HEIGHT};
        color: $text;
    }}
    Mascot.-waiting {{ color: $warning; }}
    Mascot.-done {{ color: $success; }}
    Mascot.-error {{ color: $error; }}
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state = MascotState.IDLE
        self._frame = 0
        self._plays = 0
        self._timer = None

    def on_mount(self) -> None:
        self._restart()

    @property
    def is_playing_one_shot(self) -> bool:
        """True while a play-N-times state is still running, and shouldn't be
        cut off partway through."""
        return not _SPECS[self._state].loop and self._timer is not None

    def set_state(self, state: MascotState) -> None:
        """Switch animations, restarting from the first frame. Re-setting the
        current state is ignored, so a poll loop can assert it every tick."""
        if state == self._state:
            return
        self._state = state
        for name in set(_TINTS.values()):
            self.set_class(_TINTS.get(state) == name, name)
        self._restart()

    def _frames(self) -> list[list[str]]:
        spec = _SPECS[self._state]
        return mascot_frames.FRAMES.get(spec.frames) \
            or mascot_frames.FRAMES[spec.fallback]

    def _restart(self) -> None:
        if not self.is_mounted:     # on_mount starts the loop instead
            return
        if self._timer is not None:
            self._timer.stop()
        self._frame = 0
        self._plays = 0
        self._draw()
        self._timer = self.set_interval(_SPECS[self._state].interval,
                                        self._advance)

    def _advance(self) -> None:
        spec = _SPECS[self._state]
        if self._frame + 1 < len(self._frames()):
            self._frame += 1
            self._draw()
            return
        self._plays += 1
        if not spec.loop and self._plays >= spec.repeat:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
            if spec.then is not None:
                self.set_state(spec.then)
            return
        self._frame = 0
        self._draw()

    def on_resize(self) -> None:
        self._draw()

    def _draw(self) -> None:
        # Centred by padding, not `text-align: center`: Rich strips trailing
        # whitespace before aligning, which shifts frames whose right-hand
        # column is transparent a cell over from those whose isn't.
        pad = " " * max(0, (self.content_size.width - mascot_frames.WIDTH) // 2)
        self.update(Text("\n".join(pad + row for row in
                                   self._frames()[self._frame])))
