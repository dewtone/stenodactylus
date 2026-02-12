#!/usr/bin/env python3
"""GTK4-based Starboard calibration utility.

Shows a window prompting the user to press each steno key one at a time.
Detects which bit position corresponds to each key and saves the mapping.
"""

import sys
import os
import base64
import json
import select
import threading

sys.path.insert(0, os.path.dirname(__file__))

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

from stenodactylus.steno import STENO_ORDER, KEY_LABELS
from stenodactylus.starboard import _find_starboard_hidraw, _default_keymap_path


class CalibrationApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id="app.dewtone.stenodactylus.calibrate")
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        self._keymap = {}
        self._key_index = 0
        self._keys_to_calibrate = list(STENO_ORDER)
        self._fd = None
        self._running = False

        self._build_window(app)
        self._connect_starboard()

    def _build_window(self, app):
        self._window = Gtk.ApplicationWindow(application=app)
        self._window.set_title("Starboard Calibration")
        self._window.set_default_size(500, 300)

        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        vbox.set_margin_top(40)
        vbox.set_margin_bottom(40)
        vbox.set_margin_start(40)
        vbox.set_margin_end(40)
        self._window.set_child(vbox)

        self._title_label = Gtk.Label(label="Starboard Calibration")
        self._title_label.add_css_class("title-2")
        vbox.append(self._title_label)

        self._prompt_label = Gtk.Label(label="Connecting...")
        self._prompt_label.add_css_class("title-1")
        vbox.append(self._prompt_label)

        self._detail_label = Gtk.Label(label="")
        self._detail_label.add_css_class("dim-label")
        vbox.append(self._detail_label)

        self._progress_label = Gtk.Label(label="")
        vbox.append(self._progress_label)

        css = Gtk.CssProvider()
        css.load_from_string("""
            window { background-color: #1a1a1e; }
            label { color: #dddde0; }
            .title-1 { font-size: 48px; font-weight: bold; }
            .title-2 { font-size: 18px; color: #808088; }
            .dim-label { color: #606068; font-size: 14px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._window.present()

    def _connect_starboard(self):
        hidraw_path = _find_starboard_hidraw()
        if not hidraw_path:
            self._prompt_label.set_label("No Starboard found!")
            self._detail_label.set_label("Make sure the Starboard is connected via USB")
            return

        self._fd = os.open(hidraw_path, os.O_RDWR)
        os.write(self._fd, b"enable_button_state_updates\n")
        # Drain OK
        r, _, _ = select.select([self._fd], [], [], 1.0)
        if r:
            os.read(self._fd, 64)

        self._prompt_label.set_label("Release all keys")
        self._detail_label.set_label("Make sure no keys are pressed, then wait...")

        # Wait a moment, then start calibration
        GLib.timeout_add(2000, self._start_calibration)

    def _start_calibration(self):
        self._running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._show_next_key()
        return False  # Don't repeat timeout

    def _show_next_key(self):
        if self._key_index >= len(self._keys_to_calibrate):
            self._finish()
            return

        key = self._keys_to_calibrate[self._key_index]
        label = KEY_LABELS.get(key, key)
        n = self._key_index + 1
        total = len(self._keys_to_calibrate)

        self._prompt_label.set_label(f"Press:  {key}")
        self._detail_label.set_label(f"Press and release the {label} key on the Starboard")
        self._progress_label.set_label(f"{n} / {total}")
        self._waiting_for_press = True

    def _reader_loop(self):
        """Background thread: read Starboard events and post to main thread."""
        buf = b""
        while self._running:
            try:
                fd = self._fd
                if fd is None:
                    break
                r, _, _ = select.select([fd], [], [], 0.1)
                if not r:
                    continue
                data = os.read(fd, 64)
                buf += data.rstrip(b"\x00")

                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if line_str.startswith("EV "):
                        try:
                            payload = json.loads(line_str[3:])
                            if payload.get("event") == "button_state":
                                raw = base64.b64decode(payload["data"])
                                bits = set()
                                for bi, bv in enumerate(raw):
                                    for bit in range(8):
                                        if bv & (1 << bit):
                                            bits.add(bi * 8 + bit)
                                GLib.idle_add(self._on_button_state, frozenset(bits))
                        except Exception:
                            pass
            except OSError:
                break

    def _on_button_state(self, bits):
        """Called on GTK main thread when a button state event arrives."""
        if not self._waiting_for_press:
            return

        if not bits:
            # All released — ignore (we wait for a press)
            return

        # Find bits not yet mapped
        new_bits = bits - set(self._keymap.keys())
        if not new_bits:
            # All bits in this event are already mapped — could be user pressing
            # a previously-calibrated key by accident. Ignore.
            return

        # Map the new bits to the current key
        key = self._keys_to_calibrate[self._key_index]
        for b in new_bits:
            self._keymap[b] = key

        self._waiting_for_press = False
        self._key_index += 1

        # Wait for release before showing next key
        GLib.timeout_add(300, self._show_next_key)

    def _finish(self):
        self._running = False
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

        # Save keymap
        out_path = _default_keymap_path()
        with open(out_path, "w") as f:
            json.dump(
                {str(k): v for k, v in sorted(self._keymap.items())},
                f, indent=2,
            )

        self._prompt_label.set_label("Done!")
        self._detail_label.set_label(
            f"Mapped {len(self._keymap)} bit positions to {len(set(self._keymap.values()))} keys.\n"
            f"Saved to {out_path}"
        )
        self._progress_label.set_label("You can close this window and run main.py")


if __name__ == "__main__":
    app = CalibrationApp()
    app.run(sys.argv)
