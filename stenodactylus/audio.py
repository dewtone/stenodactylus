"""Pyo audio engine — typing sounds and streak-based reward sounds.

Typing voices: 12-voice round-robin pool with three-component key switch model
(impact + click + thock) adapted from Soundsmith. Blessed parameters embedded.

Reward voices: 4-voice round-robin pool with 24-step ascending chord progression
at 432 Hz tuning. Each chord is a diatonic triad in C major with all-stepwise
voice leading (no parallel 5ths/octaves). Average pitch strictly increases.
"""

import os
os.environ["PYO_GUI_WX"] = "0"

import threading
import time

import pyo

from .steno import KEY_PAN, STENO_ORDER, STENO_ORDER_INDEX

# 432 Hz tuning
A4_432 = 432.0


def _midi_to_freq_432(midi: int) -> float:
    """Convert MIDI note number to frequency in 432 Hz tuning."""
    return A4_432 * (2 ** ((midi - 69) / 12))


# 24-step ascending chord progression: diatonic triads in C major.
# Voice leading: alternating stepwise motion — bass moves up while upper
# voices hold, then upper voices move up while bass holds. No parallel
# 5ths or octaves. Average pitch strictly increases.
#
# Each entry is (MIDI_note_1, MIDI_note_2, MIDI_note_3).
REWARD_PROGRESSION = [
    (48, 52, 55),   #  1. C3  E3  G3   C
    (48, 53, 57),   #  2. C3  F3  A3   F/C
    (50, 53, 57),   #  3. D3  F3  A3   Dm
    (50, 55, 59),   #  4. D3  G3  B3   G/D
    (52, 55, 59),   #  5. E3  G3  B3   Em
    (52, 57, 60),   #  6. E3  A3  C4   Am/E
    (53, 57, 60),   #  7. F3  A3  C4   F
    (53, 59, 62),   #  8. F3  B3  D4   G/F
    (55, 59, 62),   #  9. G3  B3  D4   G
    (55, 60, 64),   # 10. G3  C4  E4   C/G
    (57, 60, 64),   # 11. A3  C4  E4   Am
    (57, 62, 65),   # 12. A3  D4  F4   Dm/A
    (59, 62, 65),   # 13. B3  D4  F4   Bdim
    (59, 64, 67),   # 14. B3  E4  G4   Em/B
    (60, 64, 67),   # 15. C4  E4  G4   C
    (60, 65, 69),   # 16. C4  F4  A4   F/C
    (62, 65, 69),   # 17. D4  F4  A4   Dm
    (62, 67, 71),   # 18. D4  G4  B4   G/D
    (64, 67, 71),   # 19. E4  G4  B4   Em
    (64, 69, 72),   # 20. E4  A4  C5   Am/E
    (65, 69, 72),   # 21. F4  A4  C5   F
    (67, 71, 74),   # 22. G4  B4  D5   G
    (69, 72, 76),   # 23. A4  C5  E5   Am
    (72, 76, 79),   # 24. C5  E5  G5   C
]

NUM_REWARD_LEVELS = len(REWARD_PROGRESSION)

# Blessed keyboard typing parameters from Soundsmith A/B testing
TYPING_PARAMS = {
    "impact_amount": 0.3743,
    "impact_freq": 374.80,
    "impact_decay_ms": 3.294,
    "click_amount": 0.7046,
    "click_freq": 4124.78,
    "click_decay_ms": 3.020,
    "thock_amount": 0.5394,
    "thock_freq": 83.47,
    "thock_decay_ms": 14.789,
    "base_gap1_ms": 3.698,
    "base_gap2_ms": 9.278,
    "force_variation": 0.2893,
    "force_amp_scale": 0.4680,
    "force_click_boost": 0.2229,
}

NUM_TYPING_VOICES = 12
NUM_REWARD_VOICES = 4


def _find_audio_device(server):
    """Find a suitable pulse/pipewire output device."""
    try:
        devices = pyo.pa_list_devices()
        # pa_list_devices prints to stdout; we need to check output devices
        out_devices = pyo.pa_get_output_devices()
        # out_devices is a tuple of (names, indices)
        names, indices = out_devices
        for name, idx in zip(names, indices):
            name_lower = name.lower()
            if "pulse" in name_lower or "pipewire" in name_lower:
                return idx
        # Fall back to default
        return pyo.pa_get_default_output()
    except Exception:
        return pyo.pa_get_default_output()


class AudioEngine:
    """Combined typing + reward audio engine using pyo."""

    def __init__(self):
        self._server = None
        self._initialized = False
        self._lock = threading.Lock()

        # Typing voice pool
        self._typing_voices = []
        self._typing_idx = 0

        # Reward voice pool
        self._reward_voices = []
        self._reward_idx = 0

    def initialize(self) -> bool:
        """Boot the pyo server and set up voice pools."""
        if self._initialized:
            return True

        try:
            self._server = pyo.Server(
                audio="portaudio", buffersize=1024, nchnls=2, duplex=0
            )
            device = _find_audio_device(self._server)
            self._server.setOutputDevice(device)
            self._server.boot()

            if not self._server.getIsBooted():
                print("Audio: server failed to boot")
                return False

            self._server.start()

            if not self._server.getIsStarted():
                print("Audio: server failed to start")
                return False

            self._setup_typing_voices()
            self._setup_reward_voices()
            self._initialized = True
            return True

        except Exception as e:
            print(f"Audio init failed: {e}")
            return False

    def shutdown(self):
        """Shut down the audio server."""
        if self._server:
            self._typing_voices.clear()
            self._reward_voices.clear()
            try:
                self._server.stop()
                self._server.shutdown()
            except Exception:
                pass
            self._initialized = False

    # ── Typing voice pool ──────────────────────────────────────────

    def _setup_typing_voices(self):
        """Pre-allocate typing voice pool (3-component key switch model)."""
        self._typing_voices = []

        for _ in range(NUM_TYPING_VOICES):
            pan_sig = pyo.Sig(0.5)
            impact_amp = pyo.Sig(0.0)
            click_amp = pyo.Sig(0.0)
            thock_amp = pyo.Sig(0.0)
            impact_freq_sig = pyo.Sig(TYPING_PARAMS["impact_freq"])
            click_freq_sig = pyo.Sig(TYPING_PARAMS["click_freq"])
            thock_freq_sig = pyo.Sig(TYPING_PARAMS["thock_freq"])

            # Impact: soft low-freq thud
            impact_env = pyo.Adsr(
                attack=0.001, decay=0.004, sustain=0, release=0.001,
                dur=0.006, mul=impact_amp
            )
            impact_noise = pyo.Noise(mul=impact_env)
            impact_filt = pyo.ButLP(impact_noise, freq=impact_freq_sig)

            # Click: sharp metallic
            click_env = pyo.Adsr(
                attack=0.0005, decay=0.002, sustain=0, release=0.0005,
                dur=0.003, mul=click_amp
            )
            click_noise = pyo.Noise(mul=click_env)
            click_filt = pyo.ButBP(click_noise, freq=click_freq_sig, q=1.0)

            # Thock: deep thump
            thock_env = pyo.Adsr(
                attack=0.001, decay=0.006, sustain=0, release=0.002,
                dur=0.009, mul=thock_amp
            )
            thock_noise = pyo.Noise(mul=thock_env)
            thock_filt = pyo.ButLP(thock_noise, freq=thock_freq_sig)

            mix = pyo.Mix([impact_filt, click_filt, thock_filt], voices=1, mul=0.4)
            clipped = pyo.Clip(mix, min=-0.9, max=0.9)
            panned = pyo.Pan(clipped, pan=pan_sig).out()

            self._typing_voices.append({
                "pan": pan_sig,
                "impact_amp": impact_amp,
                "click_amp": click_amp,
                "thock_amp": thock_amp,
                "impact_freq": impact_freq_sig,
                "click_freq": click_freq_sig,
                "thock_freq": thock_freq_sig,
                "impact_env": impact_env,
                "click_env": click_env,
                "thock_env": thock_env,
            })

    def play_typing_burst(self, chord: frozenset):
        """Play rapid typing sounds for all keys in a chord.

        One transient per key, ~5ms spacing, stereo-panned by key position.
        Runs in a thread to avoid blocking the GTK main loop.
        """
        if not self._initialized:
            return

        # Sort keys in steno order for consistent left-to-right panning
        keys = sorted(chord, key=lambda k: STENO_ORDER_INDEX.get(k, 99))
        threading.Thread(target=self._typing_burst_thread, args=(keys,), daemon=True).start()

    def _typing_burst_thread(self, keys):
        import random

        for key in keys:
            pan = (KEY_PAN.get(key, 0.0) + 1.0) / 2.0  # Convert -1..+1 to 0..1

            # Force variation
            variation = TYPING_PARAMS["force_variation"]
            force = random.uniform(1.0 - variation, 1.0 + variation)
            force_amp = 1.0 + (force - 1.0) * TYPING_PARAMS["force_amp_scale"]
            click_boost = 1.0 + (force - 1.0) * TYPING_PARAMS["force_click_boost"]

            base_amp = 0.45 * force_amp

            with self._lock:
                voice = self._typing_voices[self._typing_idx]
                self._typing_idx = (self._typing_idx + 1) % NUM_TYPING_VOICES

            voice["pan"].setValue(pan)
            voice["impact_freq"].setValue(TYPING_PARAMS["impact_freq"])
            voice["click_freq"].setValue(TYPING_PARAMS["click_freq"])
            voice["thock_freq"].setValue(TYPING_PARAMS["thock_freq"])

            voice["impact_amp"].setValue(base_amp * TYPING_PARAMS["impact_amount"])
            voice["click_amp"].setValue(base_amp * TYPING_PARAMS["click_amount"] * click_boost)
            voice["thock_amp"].setValue(base_amp * TYPING_PARAMS["thock_amount"])

            # Envelope durations
            impact_dur = TYPING_PARAMS["impact_decay_ms"] / 1000
            voice["impact_env"].setDur(impact_dur + 0.002)
            voice["impact_env"].setDecay(impact_dur)

            click_dur = TYPING_PARAMS["click_decay_ms"] / 1000
            voice["click_env"].setDur(click_dur + 0.001)
            voice["click_env"].setDecay(click_dur)

            thock_dur = TYPING_PARAMS["thock_decay_ms"] / 1000
            voice["thock_env"].setDur(thock_dur + 0.003)
            voice["thock_env"].setDecay(thock_dur)

            # Trigger with temporal offsets
            voice["impact_env"].play()
            gap1 = TYPING_PARAMS["base_gap1_ms"] / force / 1000
            time.sleep(gap1)
            voice["click_env"].play()
            gap2 = TYPING_PARAMS["base_gap2_ms"] / force / 1000
            time.sleep(gap2)
            voice["thock_env"].play()

            # Inter-key spacing (~5ms)
            time.sleep(0.005)

    # ── Reward voice pool ──────────────────────────────────────────

    def _setup_reward_voices(self):
        """Pre-allocate reward voice pool.

        Each voice has 3 oscillators (one per chord tone) sharing a single
        envelope. Frequencies are set at play time from REWARD_PROGRESSION.
        """
        self._reward_voices = []

        for _ in range(NUM_REWARD_VOICES):
            amp_sig = pyo.Sig(0.0)
            pan_sig = pyo.Sig(0.5)

            env = pyo.Adsr(
                attack=0.008, decay=0.2, sustain=0.15, release=0.15,
                dur=0.5, mul=amp_sig
            )

            # 3 chord-tone oscillators
            freq_sigs = [pyo.Sig(200.0) for _ in range(3)]
            oscs = [pyo.Sine(freq=f, mul=env * 0.25) for f in freq_sigs]

            mix = pyo.Mix(oscs, voices=1, mul=0.4)
            clipped = pyo.Clip(mix, min=-0.9, max=0.9)
            panned = pyo.Pan(clipped, pan=pan_sig).out()

            self._reward_voices.append({
                "amp": amp_sig,
                "pan": pan_sig,
                "env": env,
                "freqs": freq_sigs,
            })

    def play_reward(self, level: int):
        """Play a reward chord at the given streak level (1-24).

        Each level selects a chord from the ascending diatonic progression.
        Level 1 is already a full triad. Envelope grows with level.
        """
        if not self._initialized or level < 1:
            return

        level = min(level, NUM_REWARD_LEVELS)
        chord = REWARD_PROGRESSION[level - 1]

        with self._lock:
            voice = self._reward_voices[self._reward_idx]
            self._reward_idx = (self._reward_idx + 1) % NUM_REWARD_VOICES

        # Set chord-tone frequencies (432 Hz tuning)
        for freq_sig, midi in zip(voice["freqs"], chord):
            freq_sig.setValue(_midi_to_freq_432(midi))

        # Amplitude: audible from level 1, grows gently
        amp = 0.15 + level * 0.005
        voice["amp"].setValue(amp)

        # Slight random pan variation
        import random
        voice["pan"].setValue(0.5 + random.uniform(-0.1, 0.1))

        # Envelope: starts satisfying, grows with streak
        t = level / NUM_REWARD_LEVELS  # 0..1 normalized
        attack = 0.008
        decay = 0.15 + t * 0.25       # 0.15 → 0.40
        sustain = 0.12 + t * 0.15     # 0.12 → 0.27
        release = 0.12 + t * 0.20     # 0.12 → 0.32
        dur = attack + decay + release + 0.05

        voice["env"].setAttack(attack)
        voice["env"].setDecay(decay)
        voice["env"].setSustain(sustain)
        voice["env"].setRelease(release)
        voice["env"].setDur(dur)

        voice["env"].play()
