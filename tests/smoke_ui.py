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

        for width, height in ((1280, 854), (1536, 1024)):
            app.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
            app._draw()
            assert app._board[2] >= 60
            assert len(app.buttons) == 4
            assert not next(button for button in app.buttons if button.action == "next").enabled
            pygame.image.save(app.screen, str(screenshots / f"sokoban-{width}x{height}.png"))

        app.menu_open = True
        app._draw()
        assert all(btn.action.startswith("level:") or btn.action == "close" for btn in app.buttons)
        app.menu_open = False

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
