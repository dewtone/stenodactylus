"""QWERTY-to-steno keyboard simulator for testing without hardware.

Uses Plover-style layout mapping QWERTY keys to steno positions.
Handles GTK4 key-repeat deduplication.
"""

from typing import Callable, Optional, Set

# Plover-style QWERTY → steno mapping
# Layout:
#   q  w  e  r  t    y  u  i  o  p  [
#   a  s  d  f  g    h  j  k  l  ;  '
#               c  v  n  m
QWERTY_TO_STENO = {
    # Top row — left consonants
    "q": "S-",
    "w": "T-",
    "e": "P-",
    "r": "H-",
    # Top row — right consonants
    "y": "-F",
    "u": "-P",
    "i": "-L",
    "o": "-T",
    "p": "-D",
    # Home row — left consonants
    "a": "S-",
    "s": "K-",
    "d": "W-",
    "f": "R-",
    # Home row — right consonants
    "h": "-R",
    "j": "-B",
    "k": "-G",
    "l": "-S",
    "semicolon": "-Z",
    # Star
    "t": "*",
    "g": "*",
    # Vowels
    "c": "A",
    "v": "O",
    "n": "E",
    "m": "U",
    # Number key
    "1": "#",
}


class QWERTYSimulator:
    """Maps QWERTY key press/release events to steno key states.

    GTK4 sends repeated key-press events when a key is held. This class
    tracks physical state to deduplicate: only the first press and final
    release generate steno events.
    """

    def __init__(self):
        self._physical_pressed: Set[str] = set()  # QWERTY keys physically held
        self.on_steno_key_down: Optional[Callable] = None
        self.on_steno_key_up: Optional[Callable] = None

    def handle_key_press(self, keyval_name: str) -> bool:
        """Handle a GTK key-press event. Returns True if consumed."""
        key = keyval_name.lower()
        steno_key = QWERTY_TO_STENO.get(key)
        if steno_key is None:
            return False

        if key in self._physical_pressed:
            # Key repeat — ignore
            return True

        self._physical_pressed.add(key)

        if self.on_steno_key_down:
            self.on_steno_key_down(steno_key)

        return True

    def handle_key_release(self, keyval_name: str) -> bool:
        """Handle a GTK key-release event. Returns True if consumed."""
        key = keyval_name.lower()
        steno_key = QWERTY_TO_STENO.get(key)
        if steno_key is None:
            return False

        if key not in self._physical_pressed:
            return True

        self._physical_pressed.discard(key)

        # Check if another QWERTY key is still mapping to the same steno key.
        # E.g., both 'q' and 'a' map to 'S-'. Only send key_up when all
        # QWERTY keys for that steno key are released.
        still_held = any(
            QWERTY_TO_STENO.get(k) == steno_key
            for k in self._physical_pressed
        )

        if not still_held and self.on_steno_key_up:
            self.on_steno_key_up(steno_key)

        return True
