#!/usr/bin/env python3
"""Full-screen countdown timer.

Block digits scale up to fill whatever terminal they are given, a progress bar
drains along the bottom, the display pulses once a second like a metronome and
burns red for the final ten seconds. At zero the screen glitches to TIME'S UP
and an alarm loops until any key is pressed.

    timer 60        sixty seconds
    timer 5m        five minutes
    timer 1h30m     ninety minutes
    timer 12:30     twelve minutes thirty seconds
    timer 1:00:00   one hour
"""

import curses
import os
import random
import re
import shutil
import subprocess
import sys
import time

DEFAULT_SECONDS = 60
MAX_SECONDS = 99 * 3600 + 59 * 60 + 59
TARGET_FPS = 30
FRAME_TIME = 1.0 / TARGET_FPS
WARNING_SECONDS = 10
ALARM_INTERVAL = 1.4          # seconds between alarm sound plays
ALARM_SOUND = "/System/Library/Sounds/Glass.aiff"
GLITCH_FRAMES = 12

NOISE = "▚▞▛▜░▒#%@"
FALLBACK = {
    "█": "#", "░": ".", "▒": "+", "▚": "\\", "▞": "/", "▛": "P", "▜": "q",
    "·": ".", "▰": "=", "▱": "-",
}

# 5-row block font, scaled at draw time to fill the terminal
FONT = {
    "0": ["█████", "█   █", "█   █", "█   █", "█████"],
    "1": ["  █  ", " ██  ", "  █  ", "  █  ", "█████"],
    "2": ["█████", "    █", "█████", "█    ", "█████"],
    "3": ["█████", "    █", " ████", "    █", "█████"],
    "4": ["█   █", "█   █", "█████", "    █", "    █"],
    "5": ["█████", "█    ", "█████", "    █", "█████"],
    "6": ["█████", "█    ", "█████", "█   █", "█████"],
    "7": ["█████", "    █", "   █ ", "  █  ", "  █  "],
    "8": ["█████", "█   █", "█████", "█   █", "█████"],
    "9": ["█████", "█   █", "█████", "    █", "█████"],
    ":": [" ", "█", " ", "█", " "],
    " ": ["  ", "  ", "  ", "  ", "  "],
    "T": ["█████", "  █  ", "  █  ", "  █  ", "  █  "],
    "I": ["█████", "  █  ", "  █  ", "  █  ", "█████"],
    "M": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    "E": ["█████", "█    ", "████ ", "█    ", "█████"],
    "S": [" ████", "█    ", " ███ ", "    █", "████ "],
    "U": ["█   █", "█   █", "█   █", "█   █", "█████"],
    "P": ["████ ", "█   █", "████ ", "█    ", "█    "],
    "'": ["█", "█", " ", " ", " "],
}

DONE_TEXT = "TIME'S UP"
FONT_ROWS = 5
HUD_ROWS = 4                  # title row + gap, bar row + gap


class TimerRenderer:
    def __init__(self, stdscr, total_seconds=DEFAULT_SECONDS):
        self.stdscr = stdscr
        self.total = total_seconds
        self.remaining = float(total_seconds)
        self.last_tick = time.monotonic()
        self.is_paused = False
        self.is_done = False
        self.frame = 0
        self.glitch_until = 0
        self.last_alarm = 0.0
        self.alarm_proc = None
        self.use_unicode = True
        self.has_afplay = shutil.which("afplay") is not None and os.path.exists(ALARM_SOUND)

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
        curses.init_pair(1, curses.COLOR_WHITE, -1)    # digits
        curses.init_pair(2, curses.COLOR_RED, -1)      # final seconds / alarm
        curses.init_pair(3, curses.COLOR_GREEN, -1)    # progress bar
        curses.init_pair(4, curses.COLOR_YELLOW, -1)   # paused

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

    # ---------- time ----------

    def _advance_clock(self):
        now = time.monotonic()
        if not self.is_paused and not self.is_done:
            self.remaining -= now - self.last_tick
        self.last_tick = now
        if self.remaining <= 0 and not self.is_done:
            self.remaining = 0.0
            self.is_done = True
            self.glitch_until = self.frame + GLITCH_FRAMES

    def _display_text(self):
        seconds_left = int(self.remaining + 0.999)
        hours, rest = divmod(seconds_left, 3600)
        minutes, seconds = divmod(rest, 60)
        if self.total >= 3600:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _is_warning(self):
        return self.remaining <= WARNING_SECONDS and not self.is_done

    # ---------- block text ----------

    def _text_cells(self, text):
        rows = [""] * FONT_ROWS
        for letter in text:
            glyph = FONT.get(letter, FONT[" "])
            for i in range(FONT_ROWS):
                rows[i] += glyph[i] + " "
        rows = [row[:-1] for row in rows]
        return rows, len(rows[0])

    def _fit_scale(self, text_w, avail_h, avail_w):
        """Largest integer scale where glyphs are 2k wide × k tall (cells are ~2:1)."""
        k_h = avail_h // FONT_ROWS
        k_w = avail_w // (text_w * 2)
        return max(0, min(k_h, k_w))

    def _draw_block_text(self, text, attr, top_area, bottom_area, glitching=False, glitch_attrs=()):
        rows, text_w = self._text_cells(text)
        avail_h = bottom_area - top_area
        avail_w = self.width - 2
        k = self._fit_scale(text_w, avail_h, avail_w)

        if k == 0:
            self._draw_plain_text(text, attr, (top_area + bottom_area) // 2)
            return

        block_h = FONT_ROWS * k
        block_w = text_w * 2 * k
        top = top_area + (avail_h - block_h) // 2
        left = (self.width - block_w) // 2

        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == " ":
                    continue
                for dy in range(k):
                    y = top + r * k + dy
                    for dx in range(2 * k):
                        x = left + c * 2 * k + dx
                        draw_ch = ch
                        cell_attr = attr
                        if glitching and random.random() < 0.4:
                            draw_ch = random.choice(NOISE)
                            cell_attr = random.choice(glitch_attrs) if glitch_attrs else attr
                        self._safe_addstr(y, x, self._ch(draw_ch), cell_attr)

    def _draw_plain_text(self, text, attr, y):
        spaced = " ".join(text)
        if len(spaced) > self.width - 2:
            spaced = text
        self._safe_addstr(y, max(0, (self.width - len(spaced)) // 2), spaced, attr)

    # ---------- layers ----------

    def _draw_countdown(self):
        phase = self.remaining % 1.0
        punch = phase > 0.82                     # bold flash as each second lands
        if self.is_paused:
            attr = self._color(4, bold=True)
        elif self._is_warning():
            attr = self._color(2, bold=punch or int(self.remaining * 2) % 2 == 0)
        else:
            attr = self._color(1, bold=punch)
        self._draw_block_text(self._display_text(), attr, 2, self.height - 2)

    def _draw_done(self):
        flash_on = int(time.monotonic() * 3) % 2 == 0
        attr = self._color(2, bold=flash_on)
        glitching = self.frame < self.glitch_until
        glitch_attrs = (self._color(1, bold=True), self._color(2, bold=True))
        text = DONE_TEXT if self._text_cells(DONE_TEXT)[1] * 2 <= self.width - 2 else "0:00"
        self._draw_block_text(text, attr, 2, self.height - 2, glitching, glitch_attrs)

    def _draw_bar(self):
        y = self.height - 2
        bar_w = max(4, self.width - 4)
        fraction = self.remaining / self.total if self.total else 0
        filled = int(round(fraction * bar_w))
        pair = 2 if self._is_warning() or self.is_done else 3
        left = (self.width - bar_w) // 2
        full = self._ch("▰")
        empty = self._ch("▱")
        self._safe_addstr(y, left, full * filled, self._color(pair, bold=True))
        self._safe_addstr(y, left + filled, empty * (bar_w - filled), self._color(1))

    def _draw_hud(self):
        if self.is_done:
            label = "TIME'S UP · any key to stop"
        elif self.is_paused:
            label = f"PAUSED · {format_duration(self.total)} · [space] resume  [r]eset  [q]uit"
        else:
            label = f"TIMER · {format_duration(self.total)} · [space] pause  [r]eset  [q]uit"
        if len(label) > self.width - 2:
            label = label.split(" · ")[0]
        pair = 2 if self.is_done else 1
        self._safe_addstr(0, max(0, (self.width - len(label)) // 2),
                          label, self._color(pair, bold=True))

    # ---------- alarm ----------

    def _sound_alarm(self):
        now = time.monotonic()
        if now - self.last_alarm < ALARM_INTERVAL:
            return
        self.last_alarm = now
        curses.beep()
        if not self.has_afplay:
            return
        if self.alarm_proc is not None and self.alarm_proc.poll() is None:
            return
        try:
            self.alarm_proc = subprocess.Popen(
                ["afplay", ALARM_SOUND],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.has_afplay = False

    def _stop_alarm(self):
        if self.alarm_proc is not None and self.alarm_proc.poll() is None:
            self.alarm_proc.terminate()

    # ---------- frame ----------

    def draw_frame(self):
        self.stdscr.erase()
        self._update_size()
        self._advance_clock()

        if self.height < 5 or self.width < 12:
            try:
                self.stdscr.addstr(0, 0, self._display_text())
            except curses.error:
                pass
            self.stdscr.refresh()
            return

        if self.is_done:
            self._draw_done()
            self._sound_alarm()
        else:
            self._draw_countdown()
        self._draw_bar()
        self._draw_hud()
        self.stdscr.refresh()

    def _handle_key(self, key):
        """Returns True when the loop should exit."""
        if key == -1:
            return False
        if self.is_done:
            return True
        if key in (ord('q'), ord('Q'), 27):
            return True
        if key == ord(' '):
            self.is_paused = not self.is_paused
        elif key in (ord('r'), ord('R')):
            self.remaining = float(self.total)
            self.is_paused = False
        return False

    def run(self):
        try:
            while True:
                t0 = time.monotonic()
                if self._handle_key(self.stdscr.getch()):
                    break
                self.draw_frame()
                self.frame += 1
                elapsed = time.monotonic() - t0
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass
        finally:
            self._stop_alarm()


DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")


def parse_duration(text):
    """'90' → 90s, '5m' → 300, '1h30m' → 5400, '12:30' → 750, '1:00:00' → 3600."""
    text = text.strip().lower()
    if ":" in text:
        parts = text.split(":")
        if not all(p.isdigit() for p in parts) or len(parts) > 3:
            raise ValueError(text)
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return total
    match = DURATION_RE.match(text)
    if not match or not any(match.groups()):
        raise ValueError(text)
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_duration(total):
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def parse_args(argv):
    for arg in argv:
        if arg in ("-h", "--help"):
            print(f"usage: timer [DURATION]   (default {DEFAULT_SECONDS}s)")
            print("  DURATION: 90 | 90s | 5m | 1h30m | 12:30 | 1:00:00")
            raise SystemExit(0)
    if not argv:
        return DEFAULT_SECONDS
    try:
        total = parse_duration(argv[0])
    except ValueError:
        print(f"timer: cannot parse duration '{argv[0]}' (try 90, 5m, 1h30m, 12:30)")
        raise SystemExit(2)
    if total <= 0:
        print("timer: duration must be positive")
        raise SystemExit(2)
    return min(total, MAX_SECONDS)


def run_no_altscreen():
    """Run curses on the main screen buffer to preserve scrollback and copy/paste."""
    total = parse_args(sys.argv[1:])
    stdscr = curses.initscr()
    sys.stdout.write('\033[?1049l')
    sys.stdout.flush()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        TimerRenderer(stdscr, total).run()
    finally:
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


if __name__ == "__main__":
    run_no_altscreen()
