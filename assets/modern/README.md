# Modern Casual Puzzle — corrected asset candidates

This folder contains five sprites for the **next** Sokoban UI integration stage.
Each PNG uses an identical **96×96 RGBA** canvas and the same tile center
at **(48, 48)**. No new gameplay or renderer changes are included in this
asset-only commit.

| PNG | Visible alpha box `(x,y,w,h)` | Purpose |
|---|---|---|
| `floor.png` | `(0,0,96,96)` | Fully opaque beige tile, tested previous version |
| `wall.png` | `(3,3,90,90)` | Rounded blue wall, transparent corners |
| `crate.png` | `(8,8,80,80)` | Orange crate, centered in cell |
| `goal.png` | `(16,16,64,64)` | Green ring, transparent center |
| `player_up.png` | `(22,9,52,78)` | Blue-clothed character, centered in cell |

At runtime, blit the scaled image into the **exact cell rectangle**
`(board_x + col*tile_size, board_y + row*tile_size, tile_size, tile_size)`.
Do **not** add offsets based on sprite bounds or enlarge the player past tile
size. Draw floor first, then goals, then crates, then player.

The image generation outputs had faint stray pixels in the otherwise transparent
background. Those pixels were removed using a foreground alpha threshold and
largest-component isolation; the visible part of each sprite was then centered
before resizing. The newly generated beige floor was rejected because it had a
large transparent hole and color artifacts; the previously validated opaque
floor was retained instead.

`atlas.png` is a transparent 5×1 sprite sheet for inspection, **not** the runtime
animation strip. Side-by-side on-dark/on-light and 47px-grid tests are in
`docs/modern-*` in this PR. These are Pillow compositions, **not Pygame screenshots**.

Verification: `python -m unittest discover -s tests -v`. The sprite tests check
size, transparency, bounding rectangles, and precise anchor geometry.
Directional sprites and full game integration remain a separate step.
