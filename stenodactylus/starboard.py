"""HID communication with the Starboard keyboard (Javelin firmware).

Uses direct /dev/hidraw access (the hidapi Python library can't open the device).
Sends enable_button_state_updates, reads JSON events from a reader thread,
posts steno key state changes to the GTK main thread via GLib.idle_add.
"""

import base64
import json
import os
import select
import threading
from typing import Callable, Dict, Optional, Set

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib

STARBOARD_VID = 0xFEED
STARBOARD_PID = 0x400D

KEYMAP_FILENAME = "starboard_keymap.json"


def _default_keymap_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, KEYMAP_FILENAME)


def _find_starboard_hidraw() -> Optional[str]:
    """Find the hidraw device for the Starboard's console interface.

    The Starboard exposes 3 HID interfaces. The console (which accepts
    enable_button_state_updates) is the one that responds with 'OK'.
    We probe each matching hidraw device.
    """
    # Find all hidraw devices belonging to the Starboard
    candidates = []
    for entry in os.listdir("/sys/class/hidraw"):
        uevent_path = f"/sys/class/hidraw/{entry}/device/uevent"
        try:
            with open(uevent_path) as f:
                content = f.read()
            # HID_ID format is bus:vid:pid, each 8 hex digits zero-padded
            vid_pid = f"{STARBOARD_VID:08X}:{STARBOARD_PID:08X}"
            if vid_pid.upper() in content.upper():
                candidates.append(f"/dev/{entry}")
        except (OSError, IOError):
            continue

    candidates.sort()

    # Probe each candidate for the console interface
    for path in candidates:
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            os.write(fd, b"enable_button_state_updates\n")

            # Wait for response
            r, _, _ = select.select([fd], [], [], 1.0)
            if r:
                data = os.read(fd, 64)
                text = data.rstrip(b"\x00").decode("utf-8", errors="replace")
                if "OK" in text:
                    os.close(fd)
                    return path

            os.close(fd)
        except (OSError, IOError):
            continue

    return None


class StarboardInput:
    """Reads steno key events from the Starboard keyboard over hidraw.

    Protocol:
        1. Find the correct /dev/hidrawN for the Starboard console interface
        2. Send "enable_button_state_updates\\n"
        3. Read 64-byte HID reports containing JSON event lines
        4. Parse EV {"event":"button_state","data":"<base64>"} events
        5. Decode bitmask, diff against previous state, emit key_down/key_up
    """

    def __init__(self, keymap_path: str = None):
        self._fd = None
        self._thread = None
        self._running = False
        self._prev_keys: Set[str] = set()

        self.on_key_down: Optional[Callable] = None
        self.on_key_up: Optional[Callable] = None

        # Load bit→key mapping
        self._keymap: Dict[int, str] = {}
        path = keymap_path or _default_keymap_path()
        if os.path.exists(path):
            with open(path) as f:
                raw = json.load(f)
            self._keymap = {int(k): v for k, v in raw.items()}

    def connect(self) -> bool:
        """Find and connect to the Starboard. Returns True on success."""
        if not self._keymap:
            print("Starboard: no keymap file, run calibration first")
            return False

        hidraw_path = _find_starboard_hidraw()
        if not hidraw_path:
            return False

        try:
            self._fd = os.open(hidraw_path, os.O_RDWR)
            os.write(self._fd, b"enable_button_state_updates\n")

            # Read and discard the OK response
            r, _, _ = select.select([self._fd], [], [], 1.0)
            if r:
                os.read(self._fd, 64)

            print(f"Starboard: connected via {hidraw_path}")
            return True
        except (OSError, IOError) as e:
            print(f"Starboard: connect failed: {e}")
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            return False

    def start(self):
        """Start the reader thread."""
        if self._fd is None or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the reader thread and close the device."""
        self._running = False
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def _reader_loop(self):
        """Read HID reports and parse button state events."""
        buf = b""

        while self._running:
            try:
                r, _, _ = select.select([self._fd], [], [], 0.1)
                if not r:
                    continue

                data = os.read(self._fd, 64)
                if not data:
                    continue

                # Strip null padding and accumulate
                buf += data.rstrip(b"\x00")

                # Process complete lines
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if line_str:
                        self._process_line(line_str)

            except OSError as e:
                if self._running:
                    print(f"Starboard: read error: {e}")
                break

        self._running = False

    def _process_line(self, line: str):
        """Parse an EV line and emit key events on the GTK main thread."""
        if not line.startswith("EV "):
            return

        try:
            payload = json.loads(line[3:])
        except json.JSONDecodeError:
            return

        if payload.get("event") != "button_state":
            return

        try:
            raw = base64.b64decode(payload.get("data", ""))
        except Exception:
            return

        current_keys = self._decode_bitmask(raw)

        pressed = current_keys - self._prev_keys
        released = self._prev_keys - current_keys
        self._prev_keys = current_keys

        for key in pressed:
            if self.on_key_down:
                GLib.idle_add(self.on_key_down, key)

        for key in released:
            if self.on_key_up:
                GLib.idle_add(self.on_key_up, key)

    def _decode_bitmask(self, raw: bytes) -> Set[str]:
        """Decode a bitmask byte array into steno key names."""
        keys = set()
        for byte_idx, byte_val in enumerate(raw):
            for bit_idx in range(8):
                if byte_val & (1 << bit_idx):
                    bit_pos = byte_idx * 8 + bit_idx
                    key = self._keymap.get(bit_pos)
                    if key:
                        keys.add(key)
        return keys


def run_calibration():
    """Interactive calibration: press each steno key, record which bit flips.

    Produces a starboard_keymap.json mapping bit positions to steno key names.
    """
    from .steno import STENO_ORDER, KEY_LABELS

    print("Starboard Calibration Utility")
    print("=" * 40)

    hidraw_path = _find_starboard_hidraw()
    if not hidraw_path:
        print("No Starboard found!")
        return

    fd = os.open(hidraw_path, os.O_RDWR)
    os.write(fd, b"enable_button_state_updates\n")

    # Drain OK
    r, _, _ = select.select([fd], [], [], 1.0)
    if r:
        os.read(fd, 64)

    print(f"Connected via {hidraw_path}")

    def read_event(timeout=5.0):
        """Read one button_state event, return raw bitmask bytes."""
        buf = b""
        deadline = __import__("time").time() + timeout
        while __import__("time").time() < deadline:
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
                            return base64.b64decode(payload["data"])
                    except Exception:
                        pass
        return None

    def drain_events():
        """Drain any pending events."""
        while True:
            r, _, _ = select.select([fd], [], [], 0.1)
            if not r:
                break
            os.read(fd, 64)

    keymap = {}

    print("\nRelease ALL keys, then press Enter...")
    input()
    drain_events()

    # Calibrate each key
    for key_name in STENO_ORDER:
        label = KEY_LABELS.get(key_name, key_name)
        print(f"\n  Press and hold: {key_name} ({label})")

        # Wait for a key-down event (any bit going from 0 to 1)
        prev_raw = None
        while True:
            raw = read_event(timeout=30)
            if raw is None:
                print("    Timeout — skipping")
                break

            bits_on = set()
            for byte_idx, byte_val in enumerate(raw):
                for bit_idx in range(8):
                    if byte_val & (1 << bit_idx):
                        bits_on.add(byte_idx * 8 + bit_idx)

            if bits_on:
                # Found a press — map any NEW bits to this key
                new_bits = bits_on - set(keymap.keys())
                if new_bits:
                    for b in new_bits:
                        keymap[b] = key_name
                    print(f"    Mapped bit(s) {sorted(new_bits)} → {key_name}")
                else:
                    # All bits already mapped — might be wrong key, show what we see
                    print(f"    Bits {sorted(bits_on)} already mapped, retrying...")
                    continue
                break
            # bits_on is empty = release event, keep waiting

        # Wait for full release
        print(f"    Release the key.")
        while True:
            raw = read_event(timeout=5)
            if raw is None:
                break
            all_off = all(b == 0 for b in raw)
            if all_off:
                break

    os.close(fd)

    # Save
    out_path = _default_keymap_path()
    # Convert int keys to str for JSON
    with open(out_path, "w") as f:
        json.dump({str(k): v for k, v in keymap.items()}, f, indent=2, sort_keys=True)

    print(f"\nCalibration complete! Mapped {len(keymap)} bits to keys.")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    run_calibration()
