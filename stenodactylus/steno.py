"""Steno key constants, layout positions, and stroke parser."""

# Canonical steno key names in steno order.
# Left-hand keys have trailing hyphen, right-hand keys have leading hyphen.
# Vowels and star have no hyphen.
STENO_ORDER = (
    "#",
    "S-", "T-", "K-", "P-", "W-", "H-", "R-",
    "A", "O",
    "*",
    "E", "U",
    "-F", "-R", "-P", "-B", "-L", "-G", "-T", "-S", "-D", "-Z",
)

STENO_ORDER_INDEX = {k: i for i, k in enumerate(STENO_ORDER)}

# Sets for classification
LEFT_KEYS = frozenset({"S-", "T-", "K-", "P-", "W-", "H-", "R-"})
VOWEL_KEYS = frozenset({"A", "O", "E", "U"})
RIGHT_KEYS = frozenset({"-F", "-R", "-P", "-B", "-L", "-G", "-T", "-S", "-D", "-Z"})
STAR_KEY = frozenset({"*"})
NUMBER_KEY = frozenset({"#"})
ALL_KEYS = frozenset(STENO_ORDER)

# Extra keys: displayed but not part of steno evaluation.
# Always light green when pressed (pinky drift indicator).
EXTRA_KEYS = frozenset({"_L1", "_L2"})

# Mapping from stroke characters to steno keys.
# The parser walks the stroke left-to-right, matching each char to the next
# position in steno order. A hyphen explicitly advances past vowels.
#
# Left bank characters (before vowels/hyphen):
#   S T K P W H R
# Vowel characters:
#   A O * E U
# Right bank characters (after vowels/hyphen):
#   F R P B L G T S D Z

# For parsing: map (character, side) → canonical key name
_LEFT_CHARS = {"S": "S-", "T": "T-", "K": "K-", "P": "P-", "W": "W-", "H": "H-", "R": "R-"}
_VOWEL_CHARS = {"A": "A", "O": "O", "*": "*", "E": "E", "U": "U"}
_RIGHT_CHARS = {"F": "-F", "R": "-R", "P": "-P", "B": "-B", "L": "-L", "G": "-G", "T": "-T", "S": "-S", "D": "-D", "Z": "-Z"}

# Characters that appear on both sides
_AMBIGUOUS_CHARS = {"S", "T", "P", "R"}


def parse_stroke(stroke: str) -> frozenset:
    """Parse a steno stroke string into a frozenset of canonical key names.

    The parser tracks position in steno order. Each character is matched to
    the next valid key at or after the current position. A hyphen explicitly
    advances position past the vowels (to disambiguate e.g. T- vs -T).

    Examples:
        parse_stroke("STKPW") → frozenset({"S-", "T-", "K-", "P-", "W-"})
        parse_stroke("RAOEUT") → frozenset({"R-", "A", "O", "E", "U", "-T"})
        parse_stroke("TPH-PB") → frozenset({"T-", "P-", "H-", "-P", "-B"})
        parse_stroke("-T") → frozenset({"-T"})
        parse_stroke("*ERT") → frozenset({"*", "E", "R-"... no...})
    """
    keys = set()
    pos = 0  # Current position in STENO_ORDER

    i = 0
    while i < len(stroke):
        ch = stroke[i]

        if ch == "-":
            # Hyphen: advance position past vowels to right bank
            # Find position of first right-bank key
            right_start = STENO_ORDER_INDEX["-F"]
            if pos < right_start:
                pos = right_start
            i += 1
            continue

        # Try to find this character at or after current position
        found = False
        for j in range(pos, len(STENO_ORDER)):
            key = STENO_ORDER[j]
            # Check if the character matches this key
            if _key_matches_char(key, ch):
                keys.add(key)
                pos = j + 1
                found = True
                break

        if not found:
            raise ValueError(f"Cannot place '{ch}' at position {pos} in stroke '{stroke}'")

        i += 1

    return frozenset(keys)


def _key_matches_char(key: str, ch: str) -> bool:
    """Check if a steno key matches a stroke character."""
    if key == "#":
        return ch == "#"
    if key == "*":
        return ch == "*"
    # Strip hyphens for comparison
    return key.replace("-", "") == ch


def stroke_to_string(keys: frozenset) -> str:
    """Convert a frozenset of canonical key names back to stroke notation.

    Inserts a hyphen if there are right-bank keys but no vowels/star to
    separate them from left-bank keys.
    """
    if not keys:
        return ""

    sorted_keys = sorted(keys, key=lambda k: STENO_ORDER_INDEX[k])

    has_vowel_or_star = bool(keys & (VOWEL_KEYS | STAR_KEY))
    has_left = bool(keys & LEFT_KEYS)
    has_right = bool(keys & RIGHT_KEYS)

    parts = []
    need_hyphen = has_right and not has_vowel_or_star and has_left

    for key in sorted_keys:
        if need_hyphen and key in RIGHT_KEYS and not any(k in parts for k in ["-"]):
            parts.append("-")
            need_hyphen = False
        # Strip positional hyphens from key name for output
        parts.append(key.replace("-", ""))

    result = "".join(parts)

    # Special case: only right-bank keys with no left/vowel → prefix with hyphen
    if has_right and not has_left and not has_vowel_or_star:
        if not result.startswith("-"):
            result = "-" + result

    return result


# Layout coordinates for Cairo drawing.
# Each key has (x, y, width, height) in a normalized coordinate space.
# Layout based on standard steno machine: two rows of consonants, vowels in center.
#
# Top row:    S  T  P  H  *  F  P  L  T  D
# Bottom row: S  K  W  R  *  R  B  G  S  Z
# Vowels:              A  O  E  U
# Number bar: # (full width across top)

KEY_W = 1.0
KEY_H = 1.0
GAP = 0.15

# X positions for the main grid columns
_COL_X = [i * (KEY_W + GAP) for i in range(10)]

LAYOUT = {
    # Number bar (spanning full width)
    "#": (0, 0, _COL_X[9] + KEY_W, KEY_H * 0.6),

    # Top row (y = 1.0)
    "S-":  (_COL_X[0], 1.0, KEY_W, KEY_H),
    "T-":  (_COL_X[1], 1.0, KEY_W, KEY_H),
    "P-":  (_COL_X[2], 1.0, KEY_W, KEY_H),
    "H-":  (_COL_X[3], 1.0, KEY_W, KEY_H),
    "*":   (_COL_X[4], 1.0, KEY_W, KEY_H * 2 + GAP),  # Star spans both rows
    "-F":  (_COL_X[5], 1.0, KEY_W, KEY_H),
    "-P":  (_COL_X[6], 1.0, KEY_W, KEY_H),
    "-L":  (_COL_X[7], 1.0, KEY_W, KEY_H),
    "-T":  (_COL_X[8], 1.0, KEY_W, KEY_H),
    "-D":  (_COL_X[9], 1.0, KEY_W, KEY_H),

    # Bottom row (y = 2.0 + GAP)
    # S- already placed (spans both rows visually? No — separate bottom S)
    # Actually in steno, left S is one tall key. Let's use the standard layout:
    # Top: #  T  P  H  *  F  P  L  T  D
    # Bot: S  K  W  R  *  R  B  G  S  Z
    # But S- is one key (left side), so let me adjust:

    "K-":  (_COL_X[1], 2.0 + GAP, KEY_W, KEY_H),
    "W-":  (_COL_X[2], 2.0 + GAP, KEY_W, KEY_H),
    "R-":  (_COL_X[3], 2.0 + GAP, KEY_W, KEY_H),
    # * already placed spanning both rows
    "-R":  (_COL_X[5], 2.0 + GAP, KEY_W, KEY_H),
    "-B":  (_COL_X[6], 2.0 + GAP, KEY_W, KEY_H),
    "-G":  (_COL_X[7], 2.0 + GAP, KEY_W, KEY_H),
    "-S":  (_COL_X[8], 2.0 + GAP, KEY_W, KEY_H),
    "-Z":  (_COL_X[9], 2.0 + GAP, KEY_W, KEY_H),

    # Vowels (below main grid, centered)
    "A":   (_COL_X[2] + 0.3, 3.4 + GAP, KEY_W, KEY_H),
    "O":   (_COL_X[3] + 0.3, 3.4 + GAP, KEY_W, KEY_H),
    "E":   (_COL_X[5] - 0.3, 3.4 + GAP, KEY_W, KEY_H),
    "U":   (_COL_X[6] - 0.3, 3.4 + GAP, KEY_W, KEY_H),
}

# Update S- to span both rows on the left
LAYOUT["S-"] = (_COL_X[0], 1.0, KEY_W, KEY_H * 2 + GAP)

# Extra keys: one column left of S-, top and bottom row (unlabeled)
LAYOUT["_L1"] = (-(KEY_W + GAP), 1.0, KEY_W, KEY_H)
LAYOUT["_L2"] = (-(KEY_W + GAP), 2.0 + GAP, KEY_W, KEY_H)

# Display labels (what to show on each key face)
KEY_LABELS = {
    "#": "#",
    "S-": "S", "T-": "T", "K-": "K", "P-": "P", "W-": "W", "H-": "H", "R-": "R",
    "A": "A", "O": "O", "*": "*", "E": "E", "U": "U",
    "-F": "F", "-R": "R", "-P": "P", "-B": "B", "-L": "L", "-G": "G",
    "-T": "T", "-S": "S", "-D": "D", "-Z": "Z",
}

# Stereo pan positions for audio (-1.0 = hard left, +1.0 = hard right)
# Based on physical key position on the steno machine
KEY_PAN = {}
_total_cols = 10
for key, (x, y, w, h) in LAYOUT.items():
    # Normalize x position to -1..+1 range
    center_x = x + w / 2
    max_x = _COL_X[9] + KEY_W
    KEY_PAN[key] = (center_x / max_x) * 2.0 - 1.0
