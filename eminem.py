#!/usr/bin/env python3
"""Animated ASCII homage to Eminem — one mic, three men.

Block-letter marquee cycles MARSHALL -> SLIM SHADY -> EMINEM (backwards-E) with a
glitch transition, pulsing at 86 BPM — the tempo of "Lose Yourself".
"""

import curses
import math
import time
import random
import sys

DEFAULT_BPM = 86              # "Lose Yourself"; override with `art eminem <bpm>`
MIN_BPM, MAX_BPM = 20, 300
TARGET_FPS = 30
FRAME_TIME = 1.0 / TARGET_FPS
NAME_HOLD_BEATS = 8           # beats each name holds before the glitch swap
GLITCH_FRAMES = 10

NOISE = "▚▞▛▜░▒#%@"
FALLBACK = {
    "█": "#", "░": ".", "▒": "+", "▚": "\\", "▞": "/", "▛": "P", "▜": "q",
    "·": ".",
}

# 5-row block font; only the letters the three names need
FONT = {
    "M": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    "A": [" ███ ", "█   █", "█████", "█   █", "█   █"],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "S": [" ████", "█    ", " ███ ", "    █", "████ "],
    "H": ["█   █", "█   █", "█████", "█   █", "█   █"],
    "L": ["█    ", "█    ", "█    ", "█    ", "█████"],
    "I": ["█████", "  █  ", "  █  ", "  █  ", "█████"],
    "E": ["█████", "█    ", "████ ", "█    ", "█████"],
    "Ǝ": ["█████", "    █", " ████", "    █", "█████"],
    "N": ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
    "D": ["████ ", "█   █", "█   █", "█   █", "████ "],
    "Y": ["█   █", " █ █ ", "  █  ", "  █  ", "  █  "],
    " ": ["  ", "  ", "  ", "  ", "  "],
}

NAMES = ["MARSHALL", "SLIM SHADY", "ƎMINEM"]

class EminemRenderer:
    def __init__(self, stdscr, bpm=DEFAULT_BPM):
        self.stdscr = stdscr
        self.bpm = bpm
        self.beat_time = 60.0 / bpm
        self.frame = 0
        self.start = time.monotonic()
        self.last_beat = -1
        self.name_idx = 0
        self.glitch_until = 0
        self.use_unicode = True

        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)

        self._setup_colors()
        self._check_unicode()
        self._update_size()

    def _setup_colors(self):
        if not curses.has_colors():
            self.has_color = False
            return
        self.has_color = True
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, -1)    # Marshall / Eminem name
        curses.init_pair(2, curses.COLOR_RED, -1)      # Slim Shady / accents

    def _check_unicode(self):
        try:
            "█".encode(self.stdscr.encoding if hasattr(self.stdscr, 'encoding') else 'utf-8')
        except (UnicodeEncodeError, LookupError):
            self.use_unicode = False

    def _ch(self, c):
        if self.use_unicode:
            return c
        return FALLBACK.get(c, c)

    def _update_size(self):
        self.height, self.width = self.stdscr.getmaxyx()

    def _color(self, pair_num, bold=False):
        if not self.has_color:
            return curses.A_BOLD if bold else curses.A_NORMAL
        attr = curses.color_pair(pair_num)
        if bold:
            attr |= curses.A_BOLD
        return attr

    def _safe_addstr(self, y, x, ch, attr=0):
        if 0 <= y < self.height and 0 <= x < self.width:
            try:
                self.stdscr.addstr(y, x, ch, attr)
            except curses.error:
                pass

    def _beat_phase(self):
        elapsed = time.monotonic() - self.start
        beat_index = int(elapsed / self.beat_time)
        phase = (elapsed % self.beat_time) / self.beat_time
        return beat_index, phase

    # ---------- marquee ----------

    def _name_cells(self, name):
        """Render a name through FONT into a list of (row, col, ch) cells."""
        rows = ["", "", "", "", ""]
        for letter in name:
            glyph = FONT.get(letter, FONT[" "])
            for i in range(5):
                rows[i] += glyph[i] + " "
        cells = []
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch != " ":
                    cells.append((r, c, ch))
        return cells, len(rows[0])

    def _draw_marquee(self, phase):
        name = NAMES[self.name_idx]
        cells, name_w = self._name_cells(name)
        is_shady = name == "SLIM SHADY"
        pair = 2 if is_shady else 1
        punch = phase < 0.18                      # bold flash right on the kick
        attr = self._color(pair, bold=punch or name == "ƎMINEM")
        glitching = self.frame < self.glitch_until

        if name_w <= self.width - 2:
            top = max(1, (self.height - 8) // 2)
            left = (self.width - name_w) // 2
            for r, c, ch in cells:
                draw_ch = ch
                cell_attr = attr
                if glitching and random.random() < 0.45:
                    draw_ch = random.choice(NOISE)
                    cell_attr = self._color(random.choice((1, 2)), bold=random.random() < 0.5)
                elif name == "ƎMINEM" and c < 6:  # the backwards Ǝ burns red
                    cell_attr = self._color(2, bold=True)
                self._safe_addstr(top + r, left + c, self._ch(draw_ch), cell_attr)
            sub_y = top + 7
        else:
            # narrow terminal: letter-spaced text instead of block glyphs
            text = " ".join(name)
            if len(text) > self.width - 2:
                text = name
            top = max(1, self.height // 2 - 1)
            left = max(0, (self.width - len(text)) // 2)
            for i, ch in enumerate(text):
                draw_ch = ch
                cell_attr = attr
                if glitching and ch != " " and random.random() < 0.45:
                    draw_ch = random.choice(NOISE)
                    cell_attr = self._color(random.choice((1, 2)), bold=random.random() < 0.5)
                elif name == "ƎMINEM" and i == 0:
                    cell_attr = self._color(2, bold=True)
                self._safe_addstr(top, left + i, self._ch(draw_ch), cell_attr)
            sub_y = top + 2

        sub = "ONE MIC · THREE MEN · DETROIT"
        if len(sub) > self.width - 2:
            sub = "ONE MIC · THREE MEN"
        self._safe_addstr(sub_y, max(0, (self.width - len(sub)) // 2),
                          sub, self._color(1))

    def _draw_hud(self, beat_index):
        bar = beat_index % 4 + 1
        label = f"ƎMINEM · {self.bpm} BPM · 1/{bar}  [q]uit"
        self._safe_addstr(0, max(0, (self.width - len(label)) // 2),
                          label, self._color(1, bold=True))

    def _on_beat(self, beat_index):
        if beat_index > 0 and beat_index % NAME_HOLD_BEATS == 0:
            self.name_idx = (self.name_idx + 1) % len(NAMES)
            self.glitch_until = self.frame + GLITCH_FRAMES

    def draw_frame(self):
        self.stdscr.erase()
        self._update_size()

        if self.height < 7 or self.width < 24:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small")
            except curses.error:
                pass
            self.stdscr.refresh()
            return

        beat_index, phase = self._beat_phase()
        if beat_index != self.last_beat:
            self._on_beat(beat_index)
            self.last_beat = beat_index

        self._draw_marquee(phase)
        self._draw_hud(beat_index)

        self.stdscr.refresh()

    def run(self):
        try:
            while True:
                t0 = time.monotonic()
                key = self.stdscr.getch()
                if key in (ord('q'), ord('Q'), 27):
                    break
                self.draw_frame()
                self.frame += 1
                elapsed = time.monotonic() - t0
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass


def parse_bpm(argv):
    """First positional arg sets BPM (clamped). Non-numeric → default 86."""
    for arg in argv:
        if arg in ("-h", "--help"):
            print(f"usage: eminem [BPM]   (default {DEFAULT_BPM}, range {MIN_BPM}-{MAX_BPM})")
            raise SystemExit(0)
        try:
            return max(MIN_BPM, min(MAX_BPM, int(float(arg))))
        except ValueError:
            continue
    return DEFAULT_BPM


def run_no_altscreen():
    """Run curses on the main screen buffer to preserve scrollback and copy/paste."""
    bpm = parse_bpm(sys.argv[1:])
    stdscr = curses.initscr()
    sys.stdout.write('\033[?1049l')
    sys.stdout.flush()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        EminemRenderer(stdscr, bpm).run()
    finally:
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


if __name__ == "__main__":
    run_no_altscreen()
