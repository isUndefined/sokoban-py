# Sokoban design system

The board reference is `img.png`. The current header and controls use the updated design described below. Keep the game clear, friendly and consistent with this top-down 2D style when adding levels or assets.

## Composition

- Use a 1536 × 1024 virtual canvas, scaled proportionally and centered in the resizable window.
- Place the crate logo and **Sokoban** on the left, level and progress counters in a centered status plaque, and the level selector on the right.
- Center the board beneath the header. Use a square grid with a fixed 78 px logical tile size; center smaller levels without changing tile size.
- Center three equal-sized controls beneath the board: **Undo**, **Restart**, **Next level**. The next-level control is muted and disabled until the level is complete.
- The reference shows the normal gameplay state. The level menu and victory dialog are centered overlays; the victory dialog shows the result and next/restart actions, or the level menu on the last level.

## Visual language

- Frame the board with the illustrated warehouse background in `assets/flat/warehouse_background.png`, and use `assets/flat/sokoban_logo.png` for the logo. The status and action panels use the illustrated wooden frame in `assets/flat/wooden_plaque.png`, with dark inset surfaces and warm accents; keep game pieces clearly visible above the artwork.
- Draw the floor as warm cream square tiles with beige grout. Walls are muted blue tiles with darker outlines, soft corners and a light inner edge.
- Make crates warm orange wood with a dark outline and crossed planks. Goals are bright green rounded-square outlines on the floor.
- Show the small, friendly character from above, facing the direction of travel. Use consistent proportions and transparent directional animation frames.
- Use the bundled DejaVu Sans Bold throughout, varying size to establish hierarchy. Text is near-white; secondary and disabled text is muted blue-gray. Interface labels are in English.
- Group footer actions in one low-profile panel, with icons, labels and keyboard shortcut badges. Use a muted disabled state. The controls are drawn in Pygame rather than supplied by the operating system.

## Motion and interaction

- Animate the character and pushed crates between grid cells; keep movement aligned to the grid. Briefly highlight a goal when a crate reaches it.
- Reveal the victory dialog after the final movement and goal feedback finish. Dialogs own input while open, and disabled or still-appearing controls must not be clickable.
- Support keyboard movement, undo and restart as well as mouse controls. Keep the same layout and visual tokens across levels.

## Implementation

- `sokoban.py` contains the game rules and starts the graphical launcher; `sokoban_gui.py` launches `FlatSokobanApp` from `sokoban_flat.py`.
- `sokoban_flat.py` owns the current layout, colors, rendering and interaction. The game uses the separate sprites in `assets/flat/`, including the directional walking atlas `player_walk.png`, and the licensed font in `assets/fonts/`; the screenshot is a reference for the board, not a flattened game scene.
- `tests/smoke_ui.py` renders the current interface at multiple window sizes and checks interaction, animation and victory flow.
