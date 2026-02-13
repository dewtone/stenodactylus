# Stenodactylus — Session Recovery Notes

## Git Setup (resolved)

This repo lives in `/home/shared-projects/stenodactylus`, which triggers git's ownership check. Three things must be configured before any git operations work:

1. **Safe directory**: `git config --global --add safe.directory /home/shared-projects/stenodactylus`
2. **Local identity** (already set in `.git/config`):
   - `user.name = dewtone`
   - `user.email = noreply@dewtone.app`
3. **Branch**: `main` (not `master`)

Remote is `https://github.com/dewtone/stenodactylus.git` — PAT not stored, must be provided for push. User keeps PAT in `githubtoken.txt` (gitignored).

## What's gitignored

- `.claude/` — Claude Code settings
- `*.local` — local-only files (e.g., `USER_PROFILE.local` with stripped personal info)
- `__pycache__/`
- `venv/`
- `githubtoken.txt`
- `tmp/` — contains Jeff's phrasing trainer source (local reference copy)

## Architecture

Steno chord trainer for the Starboard keyboard (Javelin firmware, HID communication). GTK4/Python/Cairo. Audio via pyo (portaudio), 432 Hz tuning throughout.

### Source modules (`stenodactylus/`)

| File | Purpose |
|------|---------|
| `app.py` | GTK4 Application — main window, input routing, chord lifecycle |
| `audio.py` | Pyo audio engine — typing sounds (12-voice pool) + reward chords (4-voice pool, 24-step progression) |
| `chord.py` | ChordAccumulator (state machine) + ChordEvaluator (correctness checking, 5-state key coloring) |
| `dictionary.py` | Dictionary loading: word dict (`training.txt`) + phrase resolution (`training_phrases.txt`) |
| `display.py` | Cairo drawing: `StenoKeyboardWidget` (key layout) + `WordPromptWidget` (target text + progress dots) |
| `simulator.py` | QWERTYSimulator fallback when Starboard not connected |
| `starboard.py` | HID communication with Starboard keyboard (Javelin firmware, VID 0xFEED, PID 0x400D) |
| `steno.py` | Steno constants, key layout coords, `parse_stroke()` / `stroke_to_string()` |

### Data files (project root)

| File | Purpose |
|------|---------|
| `training.txt` | Tab-separated word dictionary (253 entries). Format: `word\tstroke`. Multiple lines = alternatives. |
| `training_phrases.txt` | Phrase file (174 phrases). Words only, no strokes — resolved from word dict at load time via Cartesian product of alternatives. |
| `starboard_keymap.json` | Bit-to-key mapping (26 entries). Maps Starboard HID bitmask bits to canonical steno key names. |
| `calibrate.py` | Interactive calibration utility for Starboard key mapping. |
| `main.py` | Entry point (`python main.py`). |

### Key design decisions

- **Extra keys** (`_L1`, `_L2`): Two keys left of S- on the Starboard. Displayed without labels, always green when pressed, never evaluated for chord correctness. Pinky drift indicators. Tracked separately in `app.py._extra_pressed`, bypassing ChordAccumulator entirely.
- **Multi-stroke support**: ChordEvaluator handles sequential stroke matching. Progress dots in WordPromptWidget show position in multi-stroke entries.
- **Phrase stroke resolution**: Phrases use only words from `training.txt`. Each word's alternatives are looked up, Cartesian product gives all valid stroke sequences. E.g., if "have" has strokes `[SR, SR-F]` and "the" has `[-T]`, "have the" accepts `SR/-T` or `SR-F/-T`.
- **Audio**: Typing sounds use a 3-component key switch model (impact + click + thock). Reward sounds use a 24-step ascending diatonic triad progression in C major (432 Hz), all-stepwise voice leading, no parallel 5ths/octaves. Audible from first correct answer.

## Uncommitted changes (as of session 3)

These changes exist on disk but have NOT been committed or pushed:

1. **`stenodactylus/dictionary.py`** — Added `_build_word_lookup()`, `load_phrases()` with Cartesian product, updated `load_default_dictionary()` to load both files.
2. **`stenodactylus/display.py`** — Text overflow handling in WordPromptWidget: measures text width, shrinks font if it exceeds available width. Applies to both main word and stroke hint.
3. **`stenodactylus/audio.py`** — Complete rewrite of reward system: replaced 10-partial single-frequency design with 24-chord ascending diatonic triad progression (3 oscillators per voice). `_midi_to_freq_432()` for 432 Hz tuning. Typing voice pool unchanged.
4. **`stenodactylus/app.py`** — Removed `min(self._streak, 10)` cap on reward level (clamping now in `play_reward()`).
5. **`training_phrases.txt`** — New file. 174 phrases in categories: subject+verb, subject+verb+object, questions, verb+preposition, longer phrases.

## Pending task: Jeff's Phrasing integration

### What Jeff's Phrasing IS

Jeff's Phrasing is a **single-stroke system** where one chord encodes an entire phrase. Example: `SWR-G` = "I go" (one stroke, not two). The stroke encodes:

- **Starter** (left consonants): subject — `SWR`=I, `KPWR`=you, `KWHR`=he, `SKWHR`=she, `KPWH`=it, `TWR`=we, `TWH`=they, etc.
- **Auxiliary** (A/O vowels): `(none)`=do, `A`=can, `O`=shall, `AO`=will
- **Structure** (*EUF keys): negation, progressive, perfect, question inversion, "just", "still", "never", "even"
- **Verb** (right consonants): `G`=go, `BG`=come, `PB`=know, `BS`=say, `S`=see, etc.

**Critical**: "I don't love" as a Jeff's phrasing entry has NOTHING to do with the regular entries/strokes for "I", "don't", or "love". It is one single chord: starter(I) + structure(negation) + verb(love) = `SWR*LG`.

### What needs to be done

1. **Port JS generation logic to Python**: The source is at `tmp/phrasing-trainer/main.js`. Key functions to port:
   - `makeFull(starter, aux, structure, verb, past, hasSuffix)` → constructs stroke + phrase text
   - `conjugate(verb, form, past, hasSuffix)` → verb conjugation
   - `verbStroke(verb, past, hasSuffix)` → adds -D (past) and -T/-S (suffix) to base verb stroke
   - Data: `verbData` (65 verbs), `fullStarters` (13 subjects), `auxiliaries` (4), `structures` (16)

2. **Generate Jeff's phrasing entries**: Each entry is `phrase_text\tstroke` in training.txt format. These are single-stroke entries (not multi-stroke). Generate a reasonable subset — don't need all 65×13×4×16 = 54,080 combinations. Focus on common starters × common structures × all verbs.

3. **Add to dictionary loading**: Jeff's phrasing entries go into training.txt (or a separate file like `training_phrasing.txt`). They are loaded as normal single-stroke dictionary entries.

4. **Randomize entry selection**: Change `app.py` to pick random entries instead of sequential progression through `self._entry_idx`. User explicitly requested this.

### JS data structures reference (from `tmp/phrasing-trainer/main.js`)

Verb format: `"STROKE base past 3rd_person present_participle past_participle/suffix_word"`
- 5-form verbs: `"G go went goes going gone/to"`
- 8-form verbs (be/do/have): `"B are be am were was is being been/a"`
- Modals with `*` for missing forms: `"BGS can could can * *"` (no participles)

Stroke construction (from `makeFull`):
```
stroke = starter.stroke + aux.stroke + "-" + structure.stroke + verbStroke(verb, past, hasSuffix)
```
Then regex cleanup: `(?<=[AO])-|-(?=[*EU])` removes redundant hyphens.

`verbStroke(verb, past, hasSuffix)`:
- base = verb's stroke (first field)
- if hasSuffix: add T (or S if base already has T)
- if past: add D (or Z if base+suffix already has S)

Entries with `*` in conjugated output should be skipped (modal verbs have no participle forms).
