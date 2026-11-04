"""Headless regression check for the default top-down Pygame UI.

Run with: SDL_VIDEODRIVER=dummy python tests/smoke_ui.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402
from sokoban import Game  # noqa: E402
from sokoban_flat import DESIGN_H, DESIGN_W, FlatSokobanApp  # noqa: E402

SOLUTION = "DRDDRRRRRLLULURRRLLURR"


def exercise() -> None:
    screenshots = ROOT / "artifacts" / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    app = FlatSokobanApp()
    try:
        assert (DESIGN_W, DESIGN_H) == (1536, 1024)
        assert len(app.game.boxes) == 3
        assert len(app.game.goals) == 3
        assert app.game.moves == 0
        assert app.game.boxes_on_goals == 0
        assert all(key in app.assets for key in ("wall", "floor", "crate", "goal", "player_up"))
        assert all(f"player_{direction}" in app.assets
                   for direction in ("up", "down", "left", "right"))
        assert app.facing == "up"


        for width, height in ((1280, 854), (1536, 1024)):
            app.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
            app._draw()
            assert app._board[2] >= 60
            x0, y0, tile = app._board
            assert app._cell_origin(0, 0, x0, y0, tile) == (x0, y0)
            assert app._cell_origin(3, 2, x0, y0, tile) == (
                x0 + 3 * tile, y0 + 2 * tile)
            # Floor's visible grout is placed on logical boundaries, not
            # displaced by seams baked into the sprite image.
            occupied = app.game.walls | app.game.boxes | app.game.goals | {app.game.player}
            outside = app._outside_tiles(app.game.level.rows)
            floor_cells = [(x, y) for y, row in enumerate(app.game.level.rows)
                           for x in range(len(row)) if (x, y) not in occupied
                           and (x, y) not in outside]
            assert floor_cells
            fx, fy = floor_cells[0]
            fl, ft = app._cell_origin(fx, fy, x0, y0, tile)
            from sokoban_flat import FLOOR_GROUT, FLOOR_TILE
            assert tuple(app.canvas.get_at((fl, ft))[:3]) == FLOOR_GROUT
            assert tuple(app.canvas.get_at((fl + tile // 2, ft + tile // 2))[:3]) == FLOOR_TILE
            # No floor is drawn behind wall transparency: the wall cell
            # background is blue, never the beige floor.
            wx, wy = min(app.game.walls, key=lambda p: (p[1], p[0]))
            wall_x, wall_y = app._cell_origin(wx, wy, x0, y0, tile)
            wall_corner = app.canvas.get_at((wall_x + 1, wall_y + 1))
            assert wall_corner.b > wall_corner.r
            # An isolated interior wall must reveal beige grout through
            # rounded corners, not the dark navy outside-of-board backdrop.
            assert (7, 3) in app.game.walls
            ix, iy = app._cell_origin(7, 3, x0, y0, tile)
            inner_corner = tuple(app.canvas.get_at((ix + 1, iy + 1))[:3])
            assert inner_corner == FLOOR_GROUT, (
                f"Interior wall corner is {inner_corner}, not floor grout")
            assert len(app.buttons) == 4
            footer = [button for button in app.buttons if button.action != "menu"]
            assert len({button.rect.width for button in footer}) == 1
            assert len({button.rect.centery for button in footer}) == 1
            assert not next(button for button in app.buttons if button.action == "next").enabled
            pygame.image.save(app.screen, str(screenshots / f"sokoban-{width}x{height}.png"))

        app.menu_open = True
        app._draw()
        assert all(btn.action.startswith("level:") or btn.action == "close" for btn in app.buttons)
        assert len({btn.rect.centerx for btn in app.buttons}) == 1
        pygame.image.save(app.screen, str(screenshots / "sokoban-level-menu.png"))
        app.menu_open = False

        # No 180-degree rotation when walking down: face is selected from
        # a separate top-down image, while its head stays at the top.
        assert app.game.player == (4, 4)
        app._move(0, 1)
        assert app.facing == "down"
        assert app.game.player == (4, 5)
        app.animation = None
        app._draw()
        pygame.image.save(app.screen, str(screenshots / "sokoban-facing-down.png"))
        app._restart()
        assert app.facing == "up"
        assert app.game.player == (4, 4)

        game = Game()
        directions = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}
        for key in SOLUTION:
            assert game.move(*directions[key]), "Invalid solution step"
        assert game.is_won and game.boxes_on_goals == 3
        app.game = game
        app._draw()
        assert any(button.action == "next" and button.enabled for button in app.buttons)
        pygame.image.save(app.screen, str(screenshots / "sokoban-victory.png"))
        assert app.game.next_level()
        assert app.game.level_index == 1 and app.game.moves == 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    exercise()
    print("Top-down Pygame headless screen and interaction checks passed")
