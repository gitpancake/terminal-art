# art

Animated ASCII art for the terminal. Pure Python 3 + curses — no dependencies.

## Pieces

| Piece | Command | What it is |
| --- | --- | --- |
| hologram | `art hologram` | Rotating 3D wireframe cube with holographic scanline effects |
| ourman | `art ourman [bpm]` | 140 BPM deep-dubstep bass visualizer — throbbing sub-bass orb, bass rings, tribal spectrum |
| city | `art city` | Night city skyline with twinkling stars and lit windows |
| watch | `art watch` | Ambient zen glyph field that reacts to commit-watcher + audio-watcher activity |
| eminem | `art eminem [bpm]` | One mic, three men — MARSHALL → SLIM SHADY → ƎMINEM block-letter marquee pulsing at 86 BPM |

Every piece runs on the main screen buffer (scrollback preserved), falls back to
plain ASCII when the terminal can't do unicode, and quits on `q`, `ESC`, or `Ctrl-C`.

## Install

Scripts run standalone (`python3 eminem.py`), or wire up the `art` command:

```sh
mkdir -p ~/.local/share/art
ln -sf "$(pwd)"/*.py ~/.local/share/art/
```

Then add to your `.zshrc`:

```sh
art() {
  local name="${1:-hologram}"
  [[ $# -gt 0 ]] && shift
  local script="$HOME/.local/share/art/${name}.py"
  if [[ ! -f "$script" ]]; then
    echo "Unknown art: $name"
    echo "Available: $(printf '%s\n' ~/.local/share/art/*.py 2>/dev/null | xargs -n1 basename -s .py | tr '\n' ' ')"
    return 1
  fi
  python3 "$script" "$@"
}
```

## Watchers (for `art watch`)

`watch.py` reads state files written by two background daemons:

- `commit-watcher.py` — polls your repos for commit activity
- `audio-watcher.py` — samples system audio levels

Copy the `*.config.example.json` files to `*.config.local`, fill them in, and run
each watcher in the background. `watch.py` degrades gracefully when the state
files are missing — you just get the ambient field without the reactivity.
