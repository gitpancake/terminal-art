# Claude Instructions

Terminal ASCII art collection. Every piece is a standalone Python 3 + curses
script — no packages, no build step, standard library only (exception:
`audio-watcher.py`, which needs `numpy` + `sounddevice`).

## House style for a new piece

Follow the existing pieces (`ourman.py` is the cleanest reference):

- One file per piece, module docstring describing the visual concept.
- Class-based renderer (`FooRenderer`) taking `stdscr` in `__init__`; 30 FPS
  frame loop in `run()` with `q`/`Q`/`ESC` and `KeyboardInterrupt` exits.
- Beat-driven pieces take an optional positional BPM arg, clamped, parsed by a
  `parse_bpm`-style helper with `-h`/`--help`.
- Unicode glyphs with an ASCII `FALLBACK` dict; route every glyph through
  `self._ch()`.
- All drawing through `_safe_addstr` (bounds-checked, swallows `curses.error`).
- Colors via `curses.init_pair` with `use_default_colors()`; guard every
  attribute lookup behind `self.has_color`.
- Adapt to terminal size — degrade the rendering (smaller font, fewer
  elements) before refusing to run. Recompute layout in `_update_size()`
  every frame so live resizes work.
- End with the `run_no_altscreen()` pattern (copy it from any piece): run on
  the main screen buffer so scrollback and copy/paste survive, restore the
  terminal in `finally`.

## Testing

No test framework. Smoke-test with a `pty.fork()` driver: spawn the piece in a
pseudo-terminal, render ~60 frames by calling `draw_frame()` directly, assert
no exception. `script -q` is not a reliable tty substitute in sandboxes.

## Conventions

- Constants at the top of the file: tempo, FPS, glyph ramps, palettes.
- Comment "why," never "what" — visual intent lives in the docstring.
- State files and locks belong in `~/.local/share/art/`; config lives outside
  the repo and is pointed at via `ART_WATCHER_CONFIG` / `ART_AUDIO_CONFIG`.
  Never commit `*.config.local`, state, or lock files (gitignored).
