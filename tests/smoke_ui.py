"""Headless regression check for the actual default Storybook Pygame UI.

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
from sokoban_theme import DESIGN_SIZE, StorybookSokobanApp  # noqa: E402

SOLUTION = "DRDDRRRRRLLULURRRLLURR"


def exercise() -> None:
    screenshots = ROOT / "artifacts" / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    app = StorybookSokobanApp()
    try:
        assert DESIGN_SIZE == (1440, 960)
        assert len(app.game.boxes) == 3
        assert len(app.game.goals) == 3
        assert app.game.moves == 0
        assert app.game.boxes_on_goals == 0
        assert all(name in app.art for name in ("floor", "wall", "crate", "goal"))
        assert len(app.hero_frames) == 4
        assert all(len(direction) == 4 for direction in app.hero_frames)

        for width, height in ((1280, 854), (1536, 1024)):
            app.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
            app._draw()
            assert app._viewport[2] > 0 and app._viewport[3] > 0
            actions = {button.action for button in app.buttons}
            assert {"settings", "undo", "restart", "next"} <= actions
            assert not next(button for button in app.buttons if button.action == "next").enabled
            pygame.image.save(app.screen, str(screenshots / f"sokoban-{width}x{height}.png"))

        game = Game()
        directions = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}
        for key in SOLUTION:
            assert game.move(*directions[key]), "Invalid solution step"
        assert game.is_won
        assert game.boxes_on_goals == 3
        app.game = game
        app.show_win_popup = True
        app._draw()
        assert any(button.action == "next" and button.enabled for button in app._popup_buttons)
        pygame.image.save(app.screen, str(screenshots / "sokoban-victory.png"))

        app._next_level()
        assert app.game.level_index == 1
        assert app.game.moves == 0
        assert app.show_win_popup
    finally:
        pygame.quit()


if __name__ == "__main__":
    exercise()
    print("Storybook Pygame headless screen and interaction checks passed")
