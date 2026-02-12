"""Chord accumulation state machine and stroke evaluation."""

from enum import Enum
from typing import Callable, List, Optional

from .steno import ALL_KEYS, STENO_ORDER_INDEX


class AccState(Enum):
    IDLE = "idle"
    BUILDING = "building"


class ChordAccumulator:
    """Accumulates key presses/releases into complete chords.

    A chord is the union of all keys pressed between stroke-start (first
    keydown after all-up) and stroke-end (all keys released).

    Callbacks:
        on_chord_complete(chord: frozenset) — emitted when all keys release
        on_state_change(chord: frozenset, pressed: frozenset) — emitted on
            every key event during building
    """

    def __init__(self):
        self.state = AccState.IDLE
        self._chord = set()       # Union of all pressed keys this stroke
        self._pressed = set()     # Currently held keys
        self.on_chord_complete: Optional[Callable] = None
        self.on_state_change: Optional[Callable] = None

    def key_down(self, key: str):
        """Register a key press."""
        if key not in ALL_KEYS:
            return

        if self.state == AccState.IDLE:
            self._chord.clear()
            self.state = AccState.BUILDING

        self._chord.add(key)
        self._pressed.add(key)

        if self.on_state_change:
            self.on_state_change(frozenset(self._chord), frozenset(self._pressed))

    def key_up(self, key: str):
        """Register a key release."""
        if key not in ALL_KEYS:
            return

        self._pressed.discard(key)

        if self.state == AccState.BUILDING:
            if self.on_state_change:
                self.on_state_change(frozenset(self._chord), frozenset(self._pressed))

            if not self._pressed:
                # All keys released → chord complete
                chord = frozenset(self._chord)
                self._chord.clear()
                self.state = AccState.IDLE
                if self.on_chord_complete:
                    self.on_chord_complete(chord)

    @property
    def chord(self) -> frozenset:
        return frozenset(self._chord)

    @property
    def pressed(self) -> frozenset:
        return frozenset(self._pressed)

    @property
    def is_building(self) -> bool:
        return self.state == AccState.BUILDING


class KeyColor(Enum):
    """Five-state visual key coloring."""
    UNTOUCHED = "untouched"
    CORRECT_HELD = "correct_held"
    CORRECT_RELEASED = "correct_released"
    WRONG_HELD = "wrong_held"
    WRONG_RELEASED = "wrong_released"


class ChordEvaluator:
    """Evaluates chords against target strokes with compatible-stroke filtering.

    For the current target word, tracks which stroke alternative and multi-stroke
    position the user is on. Provides five-state key coloring and chord matching.
    """

    def __init__(self, strokes: List[List[frozenset]]):
        """
        Args:
            strokes: list of alternatives, each a list of frozensets
                     (multi-stroke sequences).
        """
        self.strokes = strokes
        self.stroke_pos = 0  # Position in multi-stroke sequence

    @property
    def current_targets(self) -> List[frozenset]:
        """Get the set of target strokes for the current position.

        Returns one target per alternative that has a stroke at the current position.
        """
        targets = []
        for alt in self.strokes:
            if self.stroke_pos < len(alt):
                targets.append(alt[self.stroke_pos])
        return targets

    @property
    def max_sequence_length(self) -> int:
        """Longest multi-stroke alternative."""
        return max(len(alt) for alt in self.strokes) if self.strokes else 0

    def compatible_strokes(self, chord: frozenset) -> List[frozenset]:
        """Return target strokes that are still compatible with the current chord.

        A stroke is compatible if every key in the chord is also in the stroke
        (i.e., chord is a subset of stroke).
        """
        targets = self.current_targets
        return [s for s in targets if chord <= s]

    def nearest_stroke(self, chord: frozenset) -> frozenset:
        """When no strokes are compatible, find the nearest one.

        Nearest = maximum intersection size, tie-break by fewest total keys.
        """
        targets = self.current_targets
        if not targets:
            return frozenset()

        def score(s):
            return (len(chord & s), -len(s))

        return max(targets, key=score)

    def reference_stroke(self, chord: frozenset) -> frozenset:
        """Get the best reference stroke for coloring.

        If compatible strokes exist, use the one with fewest keys (tightest match).
        Otherwise fall back to nearest.
        """
        compat = self.compatible_strokes(chord)
        if compat:
            return min(compat, key=len)
        return self.nearest_stroke(chord)

    def key_colors(self, chord: frozenset, pressed: frozenset) -> dict:
        """Compute five-state coloring for all steno keys.

        Returns dict mapping key name → KeyColor.
        """
        ref = self.reference_stroke(chord)
        colors = {}

        for key in ALL_KEYS:
            if key not in chord:
                colors[key] = KeyColor.UNTOUCHED
            elif key in ref:
                if key in pressed:
                    colors[key] = KeyColor.CORRECT_HELD
                else:
                    colors[key] = KeyColor.CORRECT_RELEASED
            else:
                if key in pressed:
                    colors[key] = KeyColor.WRONG_HELD
                else:
                    colors[key] = KeyColor.WRONG_RELEASED

        return colors

    def evaluate_chord(self, chord: frozenset) -> bool:
        """Check if a completed chord matches any target at the current position.

        Returns True if the chord exactly matches any alternative's stroke
        at the current multi-stroke position.
        """
        targets = self.current_targets
        return chord in targets

    def advance(self) -> bool:
        """Advance to the next stroke in a multi-stroke sequence.

        Returns True if the word is complete (no more strokes needed).
        """
        self.stroke_pos += 1
        # Word is complete if we've passed all strokes in at least one alternative
        for alt in self.strokes:
            if self.stroke_pos >= len(alt):
                return True
        return False

    def reset(self):
        """Reset to the beginning of the stroke sequence."""
        self.stroke_pos = 0
