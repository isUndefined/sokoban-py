# Locked visual concept — Sokoban: The Lost Warehouse v1.0

This is the stable visual contract for future asset generations and gameplay changes.

## Composition (1440 × 960 virtual canvas)
- Header: logo and game title at upper left, settings at upper right.
- Game board: central-left dominant isometric stone warehouse diorama.
- HUD: permanently fixed right panel with level navigation, moves, best score, progress, undo/restart/next.
- Hint: bottom-left overlay.
- Victory: modal centred over the board, with three golden stars and next/retry/levels actions.

## Art direction
- Night-time fantasy warehouse, stylised 2.5D/isometric, warm amber lanterns.
- Muted navy/purple HUD; creamy text; orange/gold wins and wooden objects; lime-green targets and primary buttons.
- Rounded, bevelled HUD panels; gentle shadows, not flat wireframe UI.
- Same camera, shadows, light direction and proportions for every game-world asset.
- Hero: same red-hoodie boy with backpack in all 4 directions and 4 walk frames each; transparent 4×4 PNG atlas, no black matte.

## Stable implementation contract
- `sokoban.py`: pure puzzle rules, independent of presentation.
- `sokoban_gui.py`: base Pygame events/utilities and launcher.
- `sokoban_theme.py`: v1.0 locked presentation; centralised colours/layout.
- `assets/hero_walk.png`: transparent 4×4 atlas (prefer high-resolution original).
- New levels do not rearrange HUD elements or change style tokens.
- New art is prepared as individual transparent game objects or tile assets; never use a flattened screenshot as the game scene.

## Current integration
- This is the first playable-code theme pass, not pixel-identical implementation of the reference painting.
- GUI runtime tests and visual comparisons remain to be completed.
- Best-move progress is stored in `~/.sokoban-py-progress.json`.
