"""Cairo drawing widgets for steno keyboard display and word prompt."""

import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo

from .steno import LAYOUT, KEY_LABELS, ALL_KEYS, STENO_ORDER, EXTRA_KEYS
from .chord import KeyColor


# Color palette (RGBA)
COLORS = {
    KeyColor.UNTOUCHED:         (0.25, 0.25, 0.28, 1.0),
    KeyColor.CORRECT_HELD:      (0.15, 0.75, 0.30, 1.0),
    KeyColor.CORRECT_RELEASED:  (0.20, 0.45, 0.25, 0.7),
    KeyColor.WRONG_HELD:        (0.85, 0.20, 0.20, 1.0),
    KeyColor.WRONG_RELEASED:    (0.50, 0.20, 0.20, 0.7),
}

KEY_BORDER_COLOR = (0.15, 0.15, 0.18, 1.0)
KEY_TEXT_COLOR = (0.85, 0.85, 0.88, 1.0)
KEY_TEXT_COLOR_ACTIVE = (1.0, 1.0, 1.0, 1.0)
BG_COLOR = (0.10, 0.10, 0.12, 1.0)


class StenoKeyboardWidget(Gtk.DrawingArea):
    """Draws the steno keyboard layout with five-state coloring."""

    def __init__(self):
        super().__init__()
        self._key_colors = {k: KeyColor.UNTOUCHED for k in ALL_KEYS}
        self.set_draw_func(self._draw)
        self.set_content_width(500)
        self.set_content_height(250)

    def update_colors(self, colors: dict):
        """Update key colors and trigger redraw."""
        self._key_colors = colors
        self.queue_draw()

    def reset(self):
        """Reset all keys to untouched."""
        self._key_colors = {k: KeyColor.UNTOUCHED for k in ALL_KEYS}
        self.queue_draw()

    def _draw(self, area, cr, width, height):
        # Background
        cr.set_source_rgba(*BG_COLOR)
        cr.paint()

        if not LAYOUT:
            return

        # Calculate scale to fit layout in widget
        min_x = min(x for x, y, w, h in LAYOUT.values())
        max_x = max(x + w for x, y, w, h in LAYOUT.values())
        max_y = max(y + h for x, y, w, h in LAYOUT.values())
        span_x = max_x - min_x

        margin = 10
        available_w = width - 2 * margin
        available_h = height - 2 * margin

        scale_x = available_w / span_x
        scale_y = available_h / max_y
        scale = min(scale_x, scale_y)

        # Center the layout
        total_w = span_x * scale
        total_h = max_y * scale
        offset_x = margin + (available_w - total_w) / 2 - min_x * scale
        offset_y = margin + (available_h - total_h) / 2

        cr.save()
        cr.translate(offset_x, offset_y)
        cr.scale(scale, scale)

        # Draw each key (steno keys + extra keys)
        for key in list(STENO_ORDER) + sorted(EXTRA_KEYS):
            if key not in LAYOUT:
                continue

            kx, ky, kw, kh = LAYOUT[key]
            color_state = self._key_colors.get(key, KeyColor.UNTOUCHED)
            fill = COLORS[color_state]
            label = KEY_LABELS.get(key, "")

            # Rounded rectangle
            radius = 0.15
            self._rounded_rect(cr, kx, ky, kw, kh, radius)

            # Fill
            cr.set_source_rgba(*fill)
            cr.fill_preserve()

            # Border
            cr.set_source_rgba(*KEY_BORDER_COLOR)
            cr.set_line_width(0.05)
            cr.stroke()

            # Label
            if color_state in (KeyColor.CORRECT_HELD, KeyColor.WRONG_HELD):
                cr.set_source_rgba(*KEY_TEXT_COLOR_ACTIVE)
            else:
                cr.set_source_rgba(*KEY_TEXT_COLOR)

            # Center text in key
            cr.set_font_size(0.45)
            extents = cr.text_extents(label)
            tx = kx + (kw - extents.width) / 2 - extents.x_bearing
            ty = ky + (kh - extents.height) / 2 - extents.y_bearing
            cr.move_to(tx, ty)
            cr.show_text(label)

        cr.restore()

    def _rounded_rect(self, cr, x, y, w, h, r):
        """Draw a rounded rectangle path."""
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()


class WordPromptWidget(Gtk.DrawingArea):
    """Displays the current target word with multi-stroke progress dots."""

    def __init__(self):
        super().__init__()
        self._word = ""
        self._total_strokes = 1
        self._current_stroke = 0
        self._stroke_text = ""
        self.set_draw_func(self._draw)
        self.set_content_width(500)
        self.set_content_height(120)

    def set_word(self, word: str, total_strokes: int = 1, stroke_text: str = ""):
        """Set the displayed word and stroke count."""
        self._word = word
        self._total_strokes = total_strokes
        self._current_stroke = 0
        self._stroke_text = stroke_text
        self.queue_draw()

    def set_stroke_progress(self, current: int):
        """Update which stroke in a multi-stroke sequence we're on."""
        self._current_stroke = current
        self.queue_draw()

    def _draw(self, area, cr, width, height):
        # Background
        cr.set_source_rgba(*BG_COLOR)
        cr.paint()

        if not self._word:
            return

        # Main word — large centered text, shrinks to fit
        cr.set_source_rgba(0.92, 0.92, 0.95, 1.0)
        margin = 20
        max_w = width - 2 * margin
        font_size = min(height * 0.45, width * 0.08)
        cr.set_font_size(font_size)
        extents = cr.text_extents(self._word)
        if extents.width > max_w and extents.width > 0:
            font_size *= max_w / extents.width
            cr.set_font_size(font_size)
            extents = cr.text_extents(self._word)
        tx = (width - extents.width) / 2 - extents.x_bearing
        ty = height * 0.45 - extents.height / 2 - extents.y_bearing
        cr.move_to(tx, ty)
        cr.show_text(self._word)

        # Stroke hint (smaller, below word), shrinks to fit
        if self._stroke_text:
            cr.set_source_rgba(0.5, 0.5, 0.55, 0.6)
            hint_size = font_size * 0.3
            cr.set_font_size(hint_size)
            extents = cr.text_extents(self._stroke_text)
            if extents.width > max_w and extents.width > 0:
                hint_size *= max_w / extents.width
                cr.set_font_size(hint_size)
                extents = cr.text_extents(self._stroke_text)
            tx = (width - extents.width) / 2 - extents.x_bearing
            ty = height * 0.68 - extents.height / 2 - extents.y_bearing
            cr.move_to(tx, ty)
            cr.show_text(self._stroke_text)

        # Multi-stroke progress dots
        if self._total_strokes > 1:
            dot_r = 4.0
            dot_gap = 14.0
            total_w = (self._total_strokes - 1) * dot_gap
            start_x = (width - total_w) / 2
            dot_y = height * 0.85

            for i in range(self._total_strokes):
                cx = start_x + i * dot_gap
                cr.arc(cx, dot_y, dot_r, 0, 2 * math.pi)

                if i < self._current_stroke:
                    # Completed stroke
                    cr.set_source_rgba(0.15, 0.75, 0.30, 1.0)
                elif i == self._current_stroke:
                    # Current stroke
                    cr.set_source_rgba(0.92, 0.92, 0.95, 1.0)
                else:
                    # Future stroke
                    cr.set_source_rgba(0.35, 0.35, 0.40, 1.0)

                cr.fill()
