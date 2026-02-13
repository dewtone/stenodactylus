"""GTK4 Application — main window and wiring."""

import random

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

from .dictionary import load_default_dictionary, DictionaryEntry
from .chord import ChordAccumulator, ChordEvaluator, KeyColor
from .simulator import QWERTYSimulator
from .display import StenoKeyboardWidget, WordPromptWidget
from .steno import stroke_to_string, ALL_KEYS, EXTRA_KEYS


class StenodactylusApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id="app.dewtone.stenodactylus")
        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

    def _on_activate(self, app):
        # Load dictionary
        self._entries = load_default_dictionary()
        self._entry_idx = random.randrange(len(self._entries))
        self._streak = 0

        # Chord engine
        self._accumulator = ChordAccumulator()
        self._accumulator.on_chord_complete = self._on_chord_complete
        self._accumulator.on_state_change = self._on_state_change
        self._evaluator = None

        # Extra keys (displayed but not evaluated)
        self._extra_pressed = set()

        # Audio engine (lazy init, only try once)
        self._audio = None
        self._audio_tried = False

        # Build UI
        self._build_window(app)

        # Input detection
        self._setup_input()

        # Load first word
        self._load_word()

    def _build_window(self, app):
        self._window = Gtk.ApplicationWindow(application=app)
        self._window.set_title("Stenodactylus")
        self._window.set_default_size(600, 480)

        # Dark theme
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", True)

        # Main vertical layout
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._window.set_child(vbox)

        # Status bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_box.set_margin_start(12)
        status_box.set_margin_end(12)
        status_box.set_margin_top(8)
        status_box.set_margin_bottom(4)

        self._status_label = Gtk.Label(label="Initializing...")
        self._status_label.set_xalign(0)
        self._status_label.add_css_class("dim-label")
        status_box.append(self._status_label)

        # Streak counter (right-aligned)
        self._streak_label = Gtk.Label(label="")
        self._streak_label.set_xalign(1)
        self._streak_label.set_hexpand(True)
        status_box.append(self._streak_label)

        vbox.append(status_box)

        # Word prompt
        self._word_prompt = WordPromptWidget()
        self._word_prompt.set_vexpand(True)
        vbox.append(self._word_prompt)

        # Steno keyboard
        self._keyboard = StenoKeyboardWidget()
        self._keyboard.set_vexpand(True)
        vbox.append(self._keyboard)

        # Progress bar (subtle, at bottom)
        progress_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        progress_box.set_margin_start(12)
        progress_box.set_margin_end(12)
        progress_box.set_margin_top(4)
        progress_box.set_margin_bottom(8)

        self._progress_label = Gtk.Label()
        self._progress_label.set_xalign(0)
        self._progress_label.add_css_class("dim-label")
        progress_box.append(self._progress_label)

        vbox.append(progress_box)

        # Apply CSS
        css = Gtk.CssProvider()
        css.load_from_string("""
            window {
                background-color: #1a1a1e;
            }
            label {
                color: #dddde0;
            }
            .dim-label {
                color: #808088;
                font-size: 12px;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._window.present()

    def _setup_input(self):
        """Detect input source: Starboard HID or QWERTY simulator."""
        starboard = None
        try:
            from .starboard import StarboardInput
            starboard = StarboardInput()
            if starboard.connect():
                self._input_source = starboard
                starboard.on_key_down = self._handle_key_down
                starboard.on_key_up = self._handle_key_up
                starboard.start()
                self._status_label.set_label("Starboard")
                return
        except Exception:
            pass

        # Fall back to QWERTY simulator
        self._sim = QWERTYSimulator()
        self._sim.on_steno_key_down = self._handle_key_down
        self._sim.on_steno_key_up = self._handle_key_up
        self._input_source = self._sim

        # Key event controllers
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        key_ctrl.connect("key-released", self._on_key_released)
        self._window.add_controller(key_ctrl)

        self._status_label.set_label("QWERTY Simulator")

    def _handle_key_down(self, key):
        """Route key events: extra keys tracked separately, steno keys to accumulator."""
        if key in EXTRA_KEYS:
            self._extra_pressed.add(key)
            self._refresh_display()
        else:
            self._accumulator.key_down(key)

    def _handle_key_up(self, key):
        if key in EXTRA_KEYS:
            self._extra_pressed.discard(key)
            self._refresh_display()
        else:
            self._accumulator.key_up(key)

    def _add_extra_colors(self, colors):
        """Merge extra key colors into the display dict."""
        for key in EXTRA_KEYS:
            if key in self._extra_pressed:
                colors[key] = KeyColor.CORRECT_HELD
            else:
                colors[key] = KeyColor.UNTOUCHED

    def _refresh_display(self):
        """Refresh display when extra keys change."""
        if self._evaluator:
            colors = self._evaluator.key_colors(
                self._accumulator.chord, self._accumulator.pressed)
        else:
            colors = {k: KeyColor.UNTOUCHED for k in ALL_KEYS}
        self._add_extra_colors(colors)
        self._keyboard.update_colors(colors)

    def _on_shutdown(self, app):
        if self._audio:
            self._audio.shutdown()
        if hasattr(self, "_input_source") and hasattr(self._input_source, "stop"):
            self._input_source.stop()

    def _init_audio(self):
        """Lazy-initialize the audio engine (only try once)."""
        if self._audio is not None or self._audio_tried:
            return
        self._audio_tried = True
        try:
            from .audio import AudioEngine
            self._audio = AudioEngine()
            if not self._audio.initialize():
                print("Audio initialization failed, continuing without sound")
                self._audio = None
        except Exception as e:
            print(f"Audio unavailable: {e}")
            self._audio = None

    def _on_key_pressed(self, controller, keyval, keycode, state):
        name = Gdk.keyval_name(keyval)
        if name:
            print(f"[KEY DOWN] keyval_name={name!r}", flush=True)
            consumed = self._sim.handle_key_press(name)
            print(f"  consumed={consumed} accumulator.chord={self._accumulator.chord} pressed={self._accumulator.pressed}", flush=True)
            return consumed
        return False

    def _on_key_released(self, controller, keyval, keycode, state):
        name = Gdk.keyval_name(keyval)
        if name:
            print(f"[KEY UP]   keyval_name={name!r}", flush=True)
            consumed = self._sim.handle_key_release(name)
            print(f"  consumed={consumed} accumulator.state={self._accumulator.state}", flush=True)
            return consumed
        return False

    def _load_word(self):
        """Load the current dictionary entry."""
        if self._entry_idx >= len(self._entries):
            self._entry_idx = 0

        entry = self._entries[self._entry_idx]
        self._evaluator = ChordEvaluator(entry.strokes)

        # Build stroke text hint (cap at 3 alternatives for readability)
        stroke_strs = []
        for alt in entry.strokes[:3]:
            stroke_strs.append("/".join(stroke_to_string(s) for s in alt))
        stroke_text = " or ".join(stroke_strs)
        if len(entry.strokes) > 3:
            stroke_text += f" (+{len(entry.strokes) - 3} more)"

        total = self._evaluator.max_sequence_length
        self._word_prompt.set_word(entry.word, total_strokes=total, stroke_text=stroke_text)
        self._keyboard.reset()
        self._update_progress()

    def _on_state_change(self, chord: frozenset, pressed: frozenset):
        """Called on every key event during chord building."""
        if self._evaluator is None:
            return

        colors = self._evaluator.key_colors(chord, pressed)
        self._add_extra_colors(colors)
        self._keyboard.update_colors(colors)

    def _on_chord_complete(self, chord: frozenset):
        """Called when all keys are released and a chord is complete."""
        if self._evaluator is None:
            return

        # Lazy init audio on first chord
        if self._audio is None:
            self._init_audio()

        # Play typing sounds for all keys in chord
        if self._audio:
            self._audio.play_typing_burst(chord)

        correct = self._evaluator.evaluate_chord(chord)

        if correct:
            word_done = self._evaluator.advance()
            if word_done:
                # Word complete
                self._streak += 1
                self._update_streak()

                # Play reward sound
                if self._audio:
                    self._audio.play_reward(self._streak)

                # Pick a random next entry
                self._entry_idx = random.randrange(len(self._entries))
                GLib.idle_add(self._load_word)
            else:
                # Multi-stroke: advance progress dots
                self._word_prompt.set_stroke_progress(self._evaluator.stroke_pos)
                self._keyboard.reset()
        else:
            # Wrong chord — keep coloring visible briefly, then reset
            self._streak = 0
            self._update_streak()
            self._evaluator.reset()
            self._word_prompt.set_stroke_progress(0)
            GLib.timeout_add(200, self._keyboard.reset)

    def _update_streak(self):
        if self._streak > 0:
            self._streak_label.set_label(f"Streak: {self._streak}")
        else:
            self._streak_label.set_label("")

    def _update_progress(self):
        self._progress_label.set_label(f"{len(self._entries)} entries")
