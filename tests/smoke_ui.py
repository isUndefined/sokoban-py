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
from sokoban_flat import DESIGN_H, DESIGN_W, MOVE_MS, GAME_TILE_SIZE, MoveAnimation, FlatSokobanApp  # noqa: E402

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
        # The viewport must not resize the grid when switching levels.
        assert GAME_TILE_SIZE == 78
        for level_index, level in enumerate(app.game.levels):
            app.game = Game(level_index=level_index)
            origin_x, origin_y, tile = app._board_geometry()
            assert tile == 78
            cols, rows = len(level.rows[0]), len(level.rows)
            assert origin_x == (DESIGN_W - cols * 78) // 2
            assert origin_y == 118 + (784 - rows * 78) // 2
        app.game = Game()
        # Every frame shares the same 128px canvas and transparent margins.
        for direction in ("up", "down", "left", "right"):
            app.facing = direction
            for frame in range(4):
                sprite = app.assets[f"walk_{direction}_{frame}"]
                assert sprite.get_size() == (128, 128)
                assert sprite.get_at((0, 0)).a == 0
                assert app._player(78, frame).get_size() == (78, 78)
            assert app._player(78) is app._asset(f"walk_{direction}_0", 78)
            assert (pygame.image.tostring(app._player(78, 1), "RGBA") !=
                    pygame.image.tostring(app._player(78, 3), "RGBA"))
        app.facing = "up"


        for width, height in ((1280, 854), (1536, 1024)):
            app.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
            app._draw()
            assert app._board[2] == GAME_TILE_SIZE
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
        assert app.animation is not None
        for index, fraction in enumerate((0.08, 0.34, 0.60, 0.86)):
            app.animation.start = pygame.time.get_ticks() - int(MOVE_MS * fraction)
            app._draw()
            assert app.animation is not None
            pygame.image.save(app.screen, str(screenshots / f"sokoban-walk-down-{index}.png"))
        app.animation.start = pygame.time.get_ticks() - MOVE_MS - 5
        app._draw()
        assert app.animation is None
        assert app._player(78) is app._asset("walk_down_0", 78)
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
        # The rules mark the level solved before the final box reaches its
        # destination on screen. Keep the modal and Next button unavailable
        # until the visual transition has finished.
        app.animation = MoveAnimation(
            source=app.game.player, target=app.game.player,
            start=pygame.time.get_ticks(),
            box_source=next(iter(app.game.goals)),
            box_target=next(iter(app.game.goals)),
        )
        app._draw()
        assert app.game.is_won and not app._victory_ready()
        assert not any(button.action == "next" and button.enabled
                       for button in app.buttons)
        assert not any(button.action == "restart"
                       for button in app.buttons if button.rect.y == 620)
        pygame.image.save(
            app.screen, str(screenshots / "sokoban-winning-push-in-flight.png"))
        # Simulate elapsed time deterministically; no sleeps in CI.
        app.animation.start = pygame.time.get_ticks() - MOVE_MS - 10
        app._draw()
        assert app.animation is None
        assert app._victory_ready()
        assert any(button.action == "next" and button.enabled
                   for button in app.buttons)
        pygame.image.save(app.screen, str(screenshots / "sokoban-victory.png"))
        assert app.game.next_level()
        assert app.game.level_index == 1 and app.game.moves == 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    exercise()
    print("Top-down Pygame headless screen and interaction checks passed")
