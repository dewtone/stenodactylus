"""Load training dictionary: word → stroke mappings."""

import os
from dataclasses import dataclass
from itertools import product
from typing import Dict, List

from .steno import parse_stroke


@dataclass
class DictionaryEntry:
    """A training dictionary entry.

    Attributes:
        word: The target word (or phrase).
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


def _build_word_lookup(entries: List[DictionaryEntry]) -> Dict[str, List[List[frozenset]]]:
    """Build word → stroke alternatives lookup from dictionary entries."""
    lookup = {}
    for entry in entries:
        lookup[entry.word] = entry.strokes
    return lookup


def load_phrases(path: str, word_lookup: Dict[str, List[List[frozenset]]]) -> List[DictionaryEntry]:
    """Load a phrase file and resolve strokes from the word dictionary.

    Format: one phrase per line (just words, no stroke notation).
    Each word is looked up in word_lookup. The Cartesian product of all
    per-word alternatives produces the full set of stroke alternatives
    for the phrase.
    """
    entries = []

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            words = line.split()
            per_word_alts = []
            for w in words:
                if w not in word_lookup:
                    raise ValueError(
                        f"{path}:{line_num}: word {w!r} not found in word dictionary")
                per_word_alts.append(word_lookup[w])

            # Cartesian product: each combination is one alternative
            # Each word alternative is a list of strokes (possibly multi-stroke).
            # Concatenate them into a single stroke sequence.
            phrase_alts = []
            for combo in product(*per_word_alts):
                seq = []
                for word_strokes in combo:
                    seq.extend(word_strokes)
                if seq not in phrase_alts:
                    phrase_alts.append(seq)

            entries.append(DictionaryEntry(word=line, strokes=phrase_alts))

    return entries


def load_default_dictionary() -> List[DictionaryEntry]:
    """Load training.txt, training_phrases.txt, and training_phrasing.txt."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    all_entries = []

    # 1. Single words (tab-separated word<TAB>stroke)
    word_path = os.path.join(project_root, "training.txt")
    word_entries = load_dictionary(word_path)
    all_entries.extend(word_entries)

    # 2. Multi-word phrases (words only, resolved from word dictionary)
    phrase_path = os.path.join(project_root, "training_phrases.txt")
    if os.path.exists(phrase_path):
        word_lookup = _build_word_lookup(word_entries)
        all_entries.extend(load_phrases(phrase_path, word_lookup))

    # 3. Jeff's Phrasing (tab-separated phrase<TAB>stroke, single-stroke entries)
    phrasing_path = os.path.join(project_root, "training_phrasing.txt")
    if os.path.exists(phrasing_path):
        all_entries.extend(load_dictionary(phrasing_path))

    return all_entries
