"""Load training dictionary: word → stroke mappings."""

import os
from dataclasses import dataclass
from typing import List

from .steno import parse_stroke


@dataclass
class DictionaryEntry:
    """A training dictionary entry.

    Attributes:
        word: The target word.
        strokes: list of alternatives, each alternative is a list of frozensets
                 (for multi-stroke sequences like PEUBG/KHUR → [frozenset(...), frozenset(...)]).
    """
    word: str
    strokes: List[List[frozenset]]


def load_dictionary(path: str) -> List[DictionaryEntry]:
    """Load a tab-separated training dictionary.

    Format: word<TAB>stroke
    Multiple lines for same word = alternative strokes.
    Strokes with / = multi-stroke sequences.

    Returns ordered list of DictionaryEntry (preserving file order, deduped by word,
    alternatives collected).
    """
    word_strokes = {}  # word → list of stroke alternatives
    word_order = []    # preserve first-seen order

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) != 2:
                raise ValueError(f"Line {line_num}: expected tab-separated word<TAB>stroke, got: {line!r}")

            word, stroke_str = parts

            # Parse multi-stroke sequence (split on /)
            try:
                stroke_seq = [parse_stroke(s) for s in stroke_str.split("/")]
            except ValueError as e:
                raise ValueError(f"Line {line_num}: {e}") from e

            if word not in word_strokes:
                word_strokes[word] = []
                word_order.append(word)

            # Avoid duplicate alternatives
            if stroke_seq not in word_strokes[word]:
                word_strokes[word].append(stroke_seq)

    entries = []
    for word in word_order:
        entries.append(DictionaryEntry(word=word, strokes=word_strokes[word]))

    return entries


def load_default_dictionary() -> List[DictionaryEntry]:
    """Load the training.txt from the project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(project_root, "training.txt")
    return load_dictionary(path)
