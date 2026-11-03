# Sokoban Py

A graphical version of the classic Sokoban puzzle game, written in Python with Pygame Community Edition (pygame-ce). Push every crate onto a goal, one careful move at a time.

## Requirements

- Python 3.10 or newer
- pygame-ce 2.5.8 or newer

The project uses pygame-ce, a maintained, API-compatible distribution that is imported as `pygame` in Python code. It provides prebuilt wheels for Python 3.14 on supported Linux platforms.

The hero is rendered from a custom 4×4 transparent sprite sheet in `assets/hero_walk.webp`: four directions with four walk-cycle frames each. The game scales the frames to fit the current isometric board.

## Install and run

```bash
python -m pip install -r requirements.txt
python sokoban.py
```

Start at a particular level:

```bash
python sokoban.py --level 2
```

## Controls

| Key | Action |
| --- | --- |
| Arrow keys / W A S D | Move the player immediately (no Enter key) |
| Z / Backspace | Undo the previous move |
| R | Restart the current level |
| N | Move to the next level after completing the current one |
| Esc | Quit |

The level selector and action buttons can also be used with the mouse. The window can be resized.

## Optional terminal mode

The earlier text interface is still available for environments without a graphical display:

```bash
python sokoban.py --terminal
```

## Run tests

```bash
python -m unittest discover -s tests -v
```

The game rules remain independent of the graphical interface and are tested separately.
