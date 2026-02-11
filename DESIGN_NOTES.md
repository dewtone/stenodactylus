# Stenodactylus Design Notes

## Global Requirements

### Performance
- Zero perceptible UI lag from any feedback mechanism (audio, visual)
- Audio playback must never cause UI glitches or freezes

### Audio
- All sounds tuned to **432 Hz** (not 440 Hz)
- Sounds should be subtle, rich, and pleasant
- Even "negative" or "plain" feedback sounds should still be attractive

### Volume Controls
The UI should have two volume sliders:
1. **Overall Volume** - Master volume for all audio output
2. **Reward Sound Volume** - Controls the musical reward sounds relative to typing sounds

Volume calculation:
- Typing sound volume = Overall Volume
- Reward sound volume = Overall Volume × Reward Sound slider value

This allows users to adjust the balance between the functional typing feedback and the musical reward feedback independently.

### Motivation Philosophy
- Maximize intrinsic motivation by linking rewards directly to the action itself
- Avoid extrinsic-feeling rewards (delayed sounds, separate celebration screens)
- Progress visualization is critical (user has data-viz background)
- Respect the user's intelligence — no patronizing feedback

### Milestone Rewards
Special audio rewards for significant achievements (e.g., new personal best WPM).

**Requirements:**
- Milestone data must be **persisted** so rewards only trigger once per achievement
- User should NOT hear the same milestone reward again after app restart
- Initial implementation: a subtle "ding" sound played in background
- Keep it tasteful — not cheesy fanfare

**TODO before implementing:**
- Design the milestone "ding" sound using Soundsmith A/B testing
- Refine until it feels rewarding but not patronizing

---

## Hardware: Starboard Steno Keyboard

### Firmware
The Starboard runs **Javelin firmware** (not QMK). Javelin already supports real-time key state reporting via its console interface — no firmware modification needed.

### Communication Protocol
1. Connect to the Starboard over HID (it exposes a hidraw device)
2. Send the command: `enable_button_state_updates`
3. The board emits JSON events on every key state change:
   ```
   EV {"event":"button_state","data":"<base64-encoded bitmask>"}
   ```
4. Each event is a full snapshot of all keys (up/down). `AAAAAAAAAAAAAAAAAAA==` = all keys up.
5. Events fire on every state change — both press and release transitions.

### Bit Position Mapping (One-Time Setup)
Run `enable_button_state_updates`, press each steno key individually, diff the base64-decoded bitmask against all-zeros, record which bit flipped. This builds a table mapping bit positions to steno key names (S, T, K, P, W, H, R, A, O, \*, E, U, F, R, P, B, L, G, T, S, D, Z, and the # key). Automate this if possible.

### USB Access on Linux
A udev rule is needed for non-root access. The Starboard's USB ID is `FEED:400D`:
```
# /etc/udev/rules.d/99-starboard.rules
SUBSYSTEM=="hidraw", KERNELS=="*:FEED:400D.*", MODE="0666"
```
Then: `sudo udevadm control --reload-rules && sudo udevadm trigger`

### Python Library
Use `hidapi` to open the Starboard HID device, send the enable command, and read button state events.

---

## Chord Accumulation Algorithm

A chord is NOT "all keys held simultaneously at peak." Real steno is a roll — fingers land and lift at different times within a single chord.

### Definition
A stroke is the **union of all keys pressed** between stroke-start and stroke-end.

```
on first keydown after all-up:
    chord = {}
    stroke_active = true

while stroke_active:
    on any keydown:
        chord = chord ∪ {key}
    on keyup:
        if pressed == {}:   # all keys released
            stroke_active = false
            emit chord
```

A key that was pressed and released mid-chord while other keys were still held is still part of the chord. This matches Gemini protocol behavior.

---

## Compatible Stroke Filtering

The dictionary allows multiple valid strokes per word. As the user builds a chord, the set of compatible strokes narrows.

### Algorithm

```
compatible = {s ∈ strokes[word] | chord ⊆ s}
```

A stroke remains compatible as long as every key the user has pressed so far is part of that stroke.

If compatible becomes empty, fall back to the nearest stroke:
```
best = argmax over strokes[word] of |chord ∩ s|
       (tie-break: fewest total keys in s)
```

---

## Five-State Visual Key Display

Each key on the real-time display has one of five visual states based on two dimensions: correctness (is this key in a compatible stroke?) and physical state (held, released during chord, or never pressed).

| State | Condition | Color |
|---|---|---|
| Correct + held | key ∈ chord, key ∈ pressed, key ∈ compatible stroke | **Bright green** |
| Correct + released | key ∈ chord, key ∉ pressed, key ∈ compatible stroke | **Dim green** (low saturation) |
| Wrong + held | key ∈ chord, key ∈ pressed, key ∉ compatible stroke | **Bright red** |
| Wrong + released | key ∈ chord, key ∉ pressed, key ∉ compatible stroke | **Dim red** (low saturation) |
| Untouched | key ∉ chord | **Grey** |

Per-key logic each scan cycle:
```
if key not in chord:
    color = grey
else if key in compatible_stroke:
    if key in pressed:
        color = bright_green
    else:
        color = dim_green
else:
    if key in pressed:
        color = bright_red
    else:
        color = dim_red
```

The dim states are critical: a briefly tapped wrong key must remain visible as dim red, not vanish to grey. The chord union preserves the error signal.

---

## Audio Feedback — Combo Chain Mechanic

Two independent audio channels on chord completion:

### Typing Sounds (Always Fire)
On every completed chord (right or wrong), play the typerimba transients for each key in the chord in rapid succession. These are feedback about what the user DID, not judgment. A wrong chord still gets its typing sounds.

Each typing sound is **50ms** long. Keys in the chord play as a rapid burst — one typerimba transient per key, stereo-panned by key position (from Soundsmith palette).

### Reward Sounds (Streak-Based)
```
on chord_complete:
    play typing sounds for all keys in chord

    if chord matches any stroke in strokes[word]:
        streak += 1
        play reward_sound[min(streak, max_level)]
        advance to next word
    else:
        streak = 0
        # silence on reward channel — no punishment sound
```

The reward sounds form a **10-level progression** (from Soundsmith palette): each level richer and more harmonically complex than the last. Level 1 = single tone. Higher levels add harmonic depth. Level 10 = the full rich sound.

### Key Design Principles
- **Absence of reward, not punishment.** A wrong chord produces silence on the reward channel (typing sounds still play). The missing reward is the signal.
- **Streak protection is the game.** At level 7, the user cares more about the next chord than at level 1. Stakes grow organically.
- **"Psychologically fake but neurologically real."** The escalating reward signal during a streak of correct chords manufactures exaggerated success that the conscious mind recognizes as practice, but the motor system consolidates anyway. Same principle as drilling single words to >1000 WPM.

---

## Dictionary Format

Plain text, tab-separated: `word\tstroke`

Multiple entries for the same word are allowed and expected — they represent alternative valid strokes. The compatible-stroke algorithm handles this natively.

Multi-stroke entries use `/` as separator: `PEUBG/KHUR` = two sequential chords. Stenodactylus must track which chord in a multi-stroke sequence the user is on and evaluate only against the current one.

The initial dictionary is provided as a separate file (the user's personal high-frequency word list, ~200 entries).

---

## Spaced Repetition

### Standard SRS Factors
- Correctness (right/wrong)
- Review history (when last seen, past performance)

### Additional Factors for Steno
- **Accuracy**: Did user chord correctly on first attempt?
- **Latency**: Time from prompt display to correct chord
  - Faster = more mastered, deserves longer interval
  - Slower but correct = less mastered, shorter interval

---

## Technical Decisions

### Platform
- Primary: EndeavourOS with Hyprland (Wayland)
- Future: Web version for broader accessibility

### Stack
- Language: Python
- GUI: GTK4 (PyGObject)
- Database: SQLite
- HID: `hidapi` for Starboard communication
- Audio: pyo or sounddevice (Soundsmith palettes)
- Reasoning: Steno ecosystem familiarity, fast iteration, good GUI support

---

## GUI Features

### Steno Key Display
Real-time visual representation of the steno keyboard layout, with five-state coloring per key (see Five-State Visual Key Display above). Updates on every HID event from the Starboard.

### Word Prompt Area
Shows the current target word. Advances on correct chord. Shows multi-stroke progress for compound entries.

### Typing Sound Selector
- Widget allowing user to select from multiple typing sound palettes
- Options include:
  - Silent (no typing sounds)
  - Multiple sound palettes developed via Soundsmith A/B testing
- User can switch palettes at any time if they tire of one
- Selection persists across sessions

### Calendar Progress Heatmap
A calendar grid visualization showing practice history with two color-coded dimensions:

#### Dimension 1: Practice Time
- Color intensity represents minutes practiced that day
- **Critical**: The visual jump from 0 → 1 minute should be dramatic (e.g., gray → colored)
- The jump from 1 → 1000 minutes should be subtle by comparison
- Purpose: Psychologically emphasize showing up over duration
- Days without practice should appear as obvious "gaps" in the visual pattern
- Suggested implementation: logarithmic scale or stepped thresholds (0, 1-5, 5-15, 15-30, 30+)

#### Dimension 2: Typing Speed
- Second color dimension or overlay showing WPM progress
- Details TBD

#### Design Notes
- Similar to GitHub contribution graph but dual-dimensional
- Should motivate streak maintenance (don't break the chain)
- User has data-viz background — can be sophisticated

---

## Open Questions

- Exact algorithm for combining accuracy + latency into SRS interval
- Specific harmonic progression for typing sounds (to be determined via Soundsmith A/B testing)
- What data visualizations beyond the heatmap would be most motivating?
- Multi-stroke sequence UX: how to visually indicate which chord in a sequence the user is on
- Bit position map for the Starboard (needs one-time calibration run)
