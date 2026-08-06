"""The mascot's frame geometry and the state machine driving it."""

import unittest

from tuney.tui.Panes import mascot_frames
from tuney.tui.Panes.mascot import _SPECS, MascotState, resting_state


class TestFrameGeometry(unittest.TestCase):
    """A frame disagreeing on size makes the dialog jump mid-animation."""

    def test_every_frame_matches_the_declared_bounding_box(self):
        for state, frames in mascot_frames.FRAMES.items():
            for index, frame in enumerate(frames):
                with self.subTest(state=state, frame=index):
                    self.assertEqual(len(frame), mascot_frames.HEIGHT)
                    for row in frame:
                        self.assertEqual(len(row), mascot_frames.WIDTH)

    def test_frames_use_only_half_block_glyphs(self):
        allowed = set(" ▀▄█")
        for state, frames in mascot_frames.FRAMES.items():
            for frame in frames:
                with self.subTest(state=state):
                    self.assertLessEqual(set("".join(frame)), allowed)

    def test_every_state_has_frames_to_play(self):
        for state, spec in _SPECS.items():
            with self.subTest(state=state):
                self.assertTrue(
                    spec.frames in mascot_frames.FRAMES
                    or spec.fallback in mascot_frames.FRAMES,
                    f"{state} has neither {spec.frames} art nor its "
                    f"{spec.fallback} fallback")


class TestStateSpecs(unittest.TestCase):

    def test_one_shot_states_hand_back_or_hold_deliberately(self):
        # A looping state with a `then` would never reach it.
        for state, spec in _SPECS.items():
            with self.subTest(state=state):
                if spec.then is not None:
                    self.assertFalse(spec.loop)

    def test_repeat_only_means_anything_for_non_looping_states(self):
        for state, spec in _SPECS.items():
            with self.subTest(state=state):
                self.assertGreaterEqual(spec.repeat, 1)
                if spec.loop:
                    self.assertEqual(spec.repeat, 1)

    def test_success_plays_twice_before_handing_back_to_idle(self):
        spec = _SPECS[MascotState.DONE]
        self.assertEqual(spec.repeat, 2)
        self.assertEqual(spec.then, MascotState.IDLE)


class TestRestingState(unittest.TestCase):
    """A one-shot resting on itself would be restarted by the chat pane's
    twice-a-second poll and never finish."""

    def test_one_shot_states_rest_on_their_successor(self):
        self.assertEqual(resting_state(MascotState.DONE), MascotState.IDLE)
        self.assertEqual(resting_state(MascotState.INTERRUPTED),
                         MascotState.IDLE)

    def test_holding_and_looping_states_rest_on_themselves(self):
        for state, spec in _SPECS.items():
            with self.subTest(state=state):
                if spec.then is None:
                    self.assertEqual(resting_state(state), state)

    def test_every_resting_state_is_somewhere_the_mascot_can_stay(self):
        for state in MascotState:
            with self.subTest(state=state):
                rest = resting_state(state)
                self.assertIsNone(_SPECS[rest].then)

    def test_idle_is_reachable_from_every_transient_state(self):
        """Only ERROR may hold its last frame, until the next query."""
        for state, spec in _SPECS.items():
            with self.subTest(state=state):
                if not spec.loop and spec.then is None:
                    self.assertEqual(state, MascotState.ERROR)


if __name__ == "__main__":
    unittest.main()
