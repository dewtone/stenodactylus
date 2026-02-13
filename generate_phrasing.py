#!/usr/bin/env python3
"""Generate Jeff's Phrasing training entries.

Ports the generation logic from tmp/phrasing-trainer/main.js to produce
single-stroke training entries where one chord encodes an entire phrase.

Output: training_phrasing.txt (tab-separated phrase<TAB>stroke)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stenodactylus.steno import stroke_to_string

# ── Verb data (from main.js) ──────────────────────────────────────────

BE = "B are be am were was is being been/a"
DO = "RP do did does doing done/it"
HAVE = "T have had has having had/to"

VERB_DATA = [
    "RB ask asked asks asking asked",
    BE,
    "RPBG become became becomes becoming become/a",
    "BL believe believed believes believing believed/that",
    "RBLG call called calls calling called",
    "BGS can could can * *",
    "RZ care cared cares caring cared",
    "PBGZ change changed changes changing changed",
    "BG come came comes coming come/to",
    "RBGZ consider considered considers considering considered",
    DO,
    "PGS expect expected expects expecting expected/that",
    "LT feel felt feels feeling felt/like",
    "PBLG find found finds finding found/that",
    "RG forget forgot forgets forgetting forgotten/to",
    "GS get got gets getting got/to",
    "GZ give gave gives giving given",
    "G go went goes going gone/to",
    HAVE,
    "PZ happen happened happens happening happened",
    "PG hear heard hears hearing heard/that",
    "RPS hope hoped hopes hoping hoped/to",
    "PLG imagine imagined imagines imagining imagined/that",
    "PBLGSZ just just just just just",
    "PBGS keep kept keeps keeping kept",
    "PB know knew knows knowing known/that",
    "RPBS learn learned learns learning learned/to",
    "LGZ leave left leaves leaving left",
    "LS let let lets letting let",
    "BLG like liked likes liking liked/to",
    "LZ live lived lives living lived",
    "L look looked looks looking looked",
    "LG love loved loves loving loved/to",
    "RPBL make made makes making made/a",
    "PL may might may may might/be",
    "PBL mean meant means meaning meant/to",
    "PLZ move moved moves moving moved",
    "PBLGS must must must * */be",
    "RPG need needed needs needing needed/to",
    "PS put put puts putting put/it",
    "RS read read reads reading read",
    "RLS realize realized realizes realizing realized/that",
    "RLG really really really really really",
    "RL recall recalled recalls recalling recalled",
    "RPL remember remembered remembers remembering remembered/that",
    "RPLS remain remained remains remaining remained",
    "R run ran runs running run",
    "BS say said says saying said/that",
    "S see saw sees seeing seen",
    "PLS seem seemed seems seeming seemed/to",
    "BLS set set sets setting set",
    "RBL shall should shall * *",
    "RBZ show showed shows showing shown",
    "RBT take took takes taking taken",
    "RLT tell told tells telling told",
    "PBG think thought thinks thinking thought/that",
    "RT try tried tries trying tried/to",
    "RPB understand understood understands understanding understood/the",
    "Z use used uses using used",
    "P want wanted wants wanting wanted/to",
    "RBGS will would will * *",
    "RBS wish wished wishes wishing wished/to",
    "RBG work worked works working worked/on",
]

FULL_STARTERS = [
    {"stroke": "SWR", "word": "I", "form": "am"},
    {"stroke": "KPWR", "word": "you", "form": "are"},
    {"stroke": "KWHR", "word": "he", "form": "is"},
    {"stroke": "SKWHR", "word": "she", "form": "is"},
    {"stroke": "KPWH", "word": "it", "form": "is"},
    {"stroke": "TWR", "word": "we", "form": "are"},
    {"stroke": "TWH", "word": "they", "form": "are"},
    {"stroke": "STKH", "word": "this", "form": "is"},
    {"stroke": "STWH", "word": "that", "form": "is"},
    {"stroke": "STHR", "word": "there", "form": "is"},
    {"stroke": "STPHR", "word": "there", "form": "are"},
]

AUXILIARIES = [
    {
        "stroke": "",
        "positive": "x do did does x x",
        "negative": "x don't didn't doesn't x x",
    },
    {
        "stroke": "A",
        "positive": "x can could can x x",
        "negative": "x can't couldn't can't x x",
    },
    {
        "stroke": "O",
        "positive": "x shall should shall x x",
        "negative": "x shall_not shouldn't shall_not x x",
    },
    {
        "stroke": "AO",
        "positive": "x will would will x x",
        "negative": "x won't wouldn't won't x x",
    },
]

STRUCTURES = [
    {"stroke": "", "do": "HE GOES", "can": "HE CAN GO"},
    {"stroke": "*", "do": "HE DOESn't GO", "can": "HE CAN'T GO"},
    {"stroke": "U", "do": "DOES HE GO", "can": "CAN HE GO"},
    {"stroke": "*U", "do": "DOESn't HE GO", "can": "CAN'T HE GO"},
    {"stroke": "F", "do": "HE HAS GONE", "can": "HE CAN have GONE"},
    {"stroke": "*F", "do": "HE HASn't GONE", "can": "HE CAN'T have GONE"},
    {"stroke": "UF", "do": "HE just GOES", "can": "HE CAN just GO"},
    {"stroke": "*UF", "do": "HE just DOESn't GO", "can": "HE just CAN'T GO"},
    {"stroke": "E", "do": "HE IS GOING", "can": "HE CAN be GOING"},
    {"stroke": "*E", "do": "HE ISn't GOING", "can": "HE CAN'T be GOING"},
    {"stroke": "EU", "do": "HE still GOES", "can": "HE CAN still GO"},
    {"stroke": "*EU", "do": "HE still DOESn't GO", "can": "HE still CAN'T GO"},
    {"stroke": "EF", "do": "HE HAS been GOING", "can": "HE CAN have been GOING"},
    {"stroke": "*EF", "do": "HE HASn't been GOING", "can": "HE CAN'T have been GOING"},
    {"stroke": "EUF", "do": "HE never GOES", "can": "HE CAN never GO"},
    {"stroke": "*EUF", "do": "HE DOESn't even GO", "can": "HE CAN'T even GO"},
]

# ── Key mapping (characters → canonical steno key names) ──────────────

LEFT_MAP = {
    "S": "S-", "T": "T-", "K": "K-", "P": "P-",
    "W": "W-", "H": "H-", "R": "R-",
}
VOWEL_MAP = {"A": "A", "O": "O"}
STRUCT_MAP = {"*": "*", "E": "E", "U": "U", "F": "-F"}
RIGHT_MAP = {
    "F": "-F", "R": "-R", "P": "-P", "B": "-B", "L": "-L",
    "G": "-G", "T": "-T", "S": "-S", "D": "-D", "Z": "-Z",
}


def _keys_from(mapping, chars):
    return frozenset(mapping[c] for c in chars)


def verb_stroke_keys(base_keys, past, has_suffix):
    """Compute verb key set with optional suffix (T/S) and past (D/Z)."""
    keys = set(base_keys)
    if has_suffix:
        keys.add("-S" if "-T" in keys else "-T")
    if past:
        keys.add("-Z" if "-S" in keys else "-D")
    return frozenset(keys)


# ── Conjugation ────────────────────────────────────────────────────────

def conjugate(verb_str, form, past, has_suffix):
    """Conjugate a verb string for the given grammatical form.

    verb_str format: "STROKE form1 form2 ... [formN/suffix]"
    5-form verbs: base past 3rd participle past_participle
    8-form verbs: are be am were was is being been
    """
    if "/" in verb_str:
        verb_part, suffix_word = verb_str.rsplit("/", 1)
    else:
        verb_part, suffix_word = verb_str, ""

    parts = verb_part.split()
    forms = parts[1:]  # skip stroke

    # Expand 5-form verbs to 8-form
    if len(forms) == 5:
        sing, sang, sings, singing, sung = forms
        forms = [sing, sing, sing, sang, sang, sings, singing, sung]

    are, be, am, were, was, is_, being, been = forms

    if form == "am":
        c = was if past else am
    elif form == "be":
        c = be
    elif form == "are":
        c = were if past else are
    elif form == "is":
        c = was if past else is_
    elif form == "being":
        c = being
    elif form == "been":
        c = been
    else:
        raise ValueError(f"Unknown form: {form}")

    if has_suffix and suffix_word:
        c = c + " " + suffix_word

    return c.replace("_", " ")


# ── Phrase generation ──────────────────────────────────────────────────

def make_full(starter, aux, structure, verb_str, past, has_suffix):
    """Generate a single (stroke, phrase) pair for full phrasing."""
    does = conjugate(DO, starter["form"], past, False)
    has_ = conjugate(HAVE, starter["form"], past, False)
    is_ = conjugate(BE, starter["form"], past, False)
    have = conjugate(HAVE, "be", False, False)
    can = conjugate(aux["positive"], starter["form"], past, False)
    cant = conjugate(aux["negative"], starter["form"], past, False)

    template = structure["can"] if aux["stroke"] else structure["do"]

    # Sequential replacement — order matters (longer placeholders first)
    s = template
    s = s.replace("HE", starter["word"])
    s = s.replace("DOES", does)
    s = s.replace("IS", is_)
    s = s.replace("HAS", has_)
    s = s.replace("HAVE", have)
    s = s.replace("CAN'T", cant)
    s = s.replace("CAN", can)
    s = s.replace("GOING", conjugate(verb_str, "being", False, False))
    s = s.replace("GONE", conjugate(verb_str, "been", False, False))
    s = s.replace("GOES", conjugate(verb_str, starter["form"], past, has_suffix))
    s = s.replace("GO", conjugate(verb_str, "be", False, False))

    # Build stroke as frozenset of keys
    starter_keys = _keys_from(LEFT_MAP, starter["stroke"])
    aux_keys = _keys_from(VOWEL_MAP, aux["stroke"])
    struct_keys = _keys_from(STRUCT_MAP, structure["stroke"])

    base_stroke_chars = verb_str.split("/")[0].split()[0]
    base_verb_keys = _keys_from(RIGHT_MAP, base_stroke_chars)
    v_keys = verb_stroke_keys(base_verb_keys, past, has_suffix)

    chord = starter_keys | aux_keys | struct_keys | v_keys
    stroke_str = stroke_to_string(chord)

    # Normalize whitespace
    s = " ".join(s.split())

    return stroke_str, s


def generate_all():
    """Generate all valid Jeff's Phrasing entries."""
    entries = []
    seen = set()

    for starter in FULL_STARTERS:
        for aux in AUXILIARIES:
            for structure in STRUCTURES:
                for verb_str in VERB_DATA:
                    for past in (False, True):
                        suffix_opts = [False]
                        if "/" in verb_str:
                            suffix_opts.append(True)

                        for has_suffix in suffix_opts:
                            try:
                                stroke, phrase = make_full(
                                    starter, aux, structure, verb_str,
                                    past, has_suffix,
                                )
                            except Exception:
                                continue

                            # Skip entries with * (missing modal forms)
                            if "*" in phrase:
                                continue

                            # Deduplicate exact (phrase, stroke) pairs
                            key = (phrase, stroke)
                            if key in seen:
                                continue
                            seen.add(key)

                            entries.append((phrase, stroke))

    return entries


def main():
    entries = generate_all()
    entries.sort(key=lambda e: e[0].lower())

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "training_phrasing.txt"
    )
    with open(out_path, "w") as f:
        f.write("# Jeff's Phrasing — single-stroke phrase entries.\n")
        f.write("# Generated by generate_phrasing.py from tmp/phrasing-trainer/main.js\n")
        f.write("# Each stroke encodes a complete phrase in one chord.\n")
        for phrase, stroke in entries:
            f.write(f"{phrase}\t{stroke}\n")

    print(f"Generated {len(entries)} phrasing entries → {out_path}")


if __name__ == "__main__":
    main()
