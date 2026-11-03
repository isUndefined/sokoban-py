# Modern Casual Puzzle sprites (asset review)

This folder contains a **new candidate art set** from the user's approved
Sokoban mockup of 2026-11-03. It does not replace `assets/flat` or change the
running Pygame screen yet; that is the next integration phase.

| File | Meaning | Alpha |
| ---- | ------- | ----- |
| `floor.png` | beige tile, with clean rounded seams | opaque |
| `wall.png` | blue square, beveled edge | transparent corners |
| `crate.png` | orange wooden crate | transparent background |
| `goal.png` | green placement indicator | transparent interior/background |
| `player_up.png` | back-facing top-down character | transparent background |
| `atlas.png` | horizontal 5-cell preview | transparent background |

All logical asset sizes: **96 × 96 px** (atlas: 480 × 96 px). Scale these to
64–80 px tiles with Pygame `smoothscale`. Draw floor, then goal, crate, and
player in that order. The wall occupies a tile on its own.

The asset sheet is available as `assets/modern/atlas.png`. A separate
Pillow composition was visually reviewed at 64 px tile size; this is **not**
a Pygame screenshot. The existing first level and UI remain unchanged.

Limitations: this stage provides one top-down character view; directional
animation and game integration are separate, subsequent tasks. The same
illustration should not be stretched or rotated 90 degrees as a substitute for
proper directional walking frames.
