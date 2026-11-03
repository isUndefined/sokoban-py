# Sokoban Py

A small, dependency-free implementation of the classic Sokoban puzzle game in Python.

## Requirements

- Python 3.10 or newer
- No third-party packages

## Run the game

    python sokoban.py

Start at a particular level with:

    python sokoban.py --level 2

## Controls

Enter one command and press Enter:

| Command | Action |
| --- | --- |
| W / A / S / D | Move up / left / down / right |
| up / left / down / right | Alternative movement commands |
| U | Undo the previous move |
| R | Restart the current level |
| N | Go to the next level after completing the current one |
| Q | Quit |

Push every crate ($) onto a goal (.). A crate on a goal is shown as *, and the player standing on a goal is shown as +. Crates can be pushed, but never pulled.

## Run tests

    python -m unittest discover -s tests -v

The game rules are kept separate from terminal input/output in the Game class, so movement, pushing, undo, restart, and level progression can be tested independently.
