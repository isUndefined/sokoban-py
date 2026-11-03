"""Graphical Pygame interface for Sokoban."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import pygame

from sokoban import Game, LEVELS, Position


WIDTH, HEIGHT = 1160, 800
FPS = 60

BG = (17, 25, 35)
BG_SOFT = (23, 34, 46)
PANEL = (29, 42, 55)
PANEL_LIGHT = (38, 53, 68)
PANEL_BORDER = (55, 72, 88)
TEXT = (235, 240, 239)
MUTED = (151, 169, 181)
MINT = (112, 218, 179)
MINT_DARK = (53, 140, 111)
GOLD = (246, 190, 91)
FLOOR = (222, 215, 194)
FLOOR_ALT = (214, 206, 184)
WALL = (79, 91, 99)
WALL_TOP = (111, 124, 130)
WOOD = (183, 111, 61)
WOOD_LIGHT = (224, 157, 91)
WOOD_DARK = (112, 63, 39)
PLAYER = (74, 159, 194)
PLAYER_DARK = (38, 103, 138)


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str
    enabled: bool = True
    primary: bool = False


class SokobanApp:
    def __init__(self, start_level: int = 0) -> None:
        pygame.init()
        pygame.display.set_caption("Sokoban — Warehouse Puzzles")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("dejavusans", 31, bold=True)
        self.heading_font = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.body_font = pygame.font.SysFont("dejavusans", 15)
        self.small_font = pygame.font.SysFont("dejavusans", 12)
        self.number_font = pygame.font.SysFont("dejavusans", 27, bold=True)
        self.game = Game(level_index=start_level)
        self.buttons: list[Button] = []
        self.popup_button: Button | None = None
        self.running = True
        self.animation: tuple[Position, Position, Position | None, Position | None, int] | None = None
        self.toast = ""
        self.toast_until = 0
        pygame.key.set_repeat(175, 105)

    def run(self) -> None:
        while self.running:
            self._handle_events()
            self._draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                # Use event.unicode as well as key constants so WASD works
                # with both Latin and Russian keyboard layouts.
                char = event.unicode.lower()
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_UP or char in ("w", "ц"):
                    self._move(0, -1)
                elif event.key == pygame.K_DOWN or char in ("s", "ы"):
                    self._move(0, 1)
                elif event.key == pygame.K_LEFT or char in ("a", "ф"):
                    self._move(-1, 0)
                elif event.key == pygame.K_RIGHT or char in ("d", "в"):
                    self._move(1, 0)
                elif event.key == pygame.K_BACKSPACE or char in ("z", "я", "u", "г"):
                    self._undo()
                elif char in ("r", "к"):
                    self._restart()
                elif event.key == pygame.K_n or char in ("n", "т"):
                    self._next_level()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _move(self, dx: int, dy: int) -> None:
        if self.game.is_won:
            return
        old_player = self.game.player
        old_boxes = set(self.game.boxes)
        if self.game.move(dx, dy):
            pushed_from = next(iter(old_boxes - self.game.boxes), None)
            pushed_to = next(iter(self.game.boxes - old_boxes), None)
            self.animation = (old_player, self.game.player, pushed_from, pushed_to, pygame.time.get_ticks())
        else:
            self._show_toast("That way is blocked")

    def _undo(self) -> None:
        if self.game.undo():
            self.animation = None
            self._show_toast("Last move undone")
        else:
            self._show_toast("Nothing to undo")

    def _restart(self) -> None:
        self.game.restart()
        self.animation = None
        self._show_toast("Level restarted")

    def _next_level(self) -> None:
        if not self.game.is_won:
            self._show_toast("Complete the level first")
        elif not self.game.next_level():
            self._show_toast("All levels completed!")
        else:
            self.animation = None
            self._show_toast(f"Level {self.game.level_index + 1}: {self.game.level.name}")

    def _select_level(self, index: int) -> None:
        if 0 <= index < len(self.game.levels):
            self.game = Game(levels=self.game.levels, level_index=index)
            self.animation = None
            self._show_toast(f"Level {index + 1} selected")

    def _show_toast(self, message: str) -> None:
        self.toast = message
        self.toast_until = pygame.time.get_ticks() + 1500

    def _handle_click(self, pos: tuple[int, int]) -> None:
        if (
            self.popup_button is not None
            and self.popup_button.enabled
            and self.popup_button.rect.collidepoint(pos)
        ):
            self._next_level()
            return

        for button in self.buttons:
            if button.rect.collidepoint(pos) and button.enabled:
                if button.action == "undo":
                    self._undo()
                elif button.action == "restart":
                    self._restart()
                elif button.action == "next":
                    self._next_level()
                elif button.action.startswith("level:"):
                    self._select_level(int(button.action.split(":", 1)[1]))
                return

    def _draw(self) -> None:
        self.popup_button = None
        width, height = self.screen.get_size()
        self.screen.fill(BG)
        self._draw_background(width, height)
        self._draw_header(width)

        margin = 30
        top = 112
        gap = 22
        side_width = min(310, max(270, int(width * 0.28)))
        board_width = width - margin * 2 - gap - side_width
        panel_height = max(500, height - top - 28)
        board_rect = pygame.Rect(margin, top, board_width, panel_height)
        side_rect = pygame.Rect(board_rect.right + gap, top, side_width, panel_height)

        self._draw_board_panel(board_rect)
        self._draw_sidebar(side_rect)
        self._draw_toast(width, height)

    def _draw_background(self, width: int, height: int) -> None:
        for x in range(0, width, 48):
            pygame.draw.line(self.screen, (21, 31, 42), (x, 0), (x, height), 1)
        for y in range(0, height, 48):
            pygame.draw.line(self.screen, (21, 31, 42), (0, y), (width, y), 1)
        pygame.draw.circle(self.screen, (23, 45, 54), (width - 80, 70), 170, 1)
        pygame.draw.circle(self.screen, (23, 45, 54), (width - 80, 70), 205, 1)

    def _draw_header(self, width: int) -> None:
        self._text("SOKOBAN", self.title_font, TEXT, (32, 24))
        self._text("WAREHOUSE PUZZLES", self.small_font, MINT, (34, 65))
        tagline = "A little planning goes a long way."
        tag_surface = self.body_font.render(tagline, True, MUTED)
        self.screen.blit(tag_surface, (width - tag_surface.get_width() - 34, 42))
        pygame.draw.line(self.screen, PANEL_BORDER, (30, 94), (width - 30, 94), 1)

    def _draw_board_panel(self, rect: pygame.Rect) -> None:
        self._panel(rect)
        title = f"LEVEL {self.game.level_index + 1:02d}"
        self._text(title, self.small_font, MINT, (rect.x + 25, rect.y + 20))
        self._text(self.game.level.name, self.heading_font, TEXT, (rect.x + 25, rect.y + 43))
        board_area = pygame.Rect(rect.x + 20, rect.y + 92, rect.width - 40, rect.height - 118)
        self._draw_board(board_area)
        if self.game.is_won:
            self._draw_win_overlay(board_area)

    def _draw_board(self, area: pygame.Rect) -> None:
        rows = self.game.level.rows
        cols = len(rows[0])
        row_count = len(rows)
        tile = int(min(66, (area.width - 28) / cols, (area.height - 28) / row_count))
        tile = max(28, tile)
        board_w, board_h = cols * tile, row_count * tile
        origin_x = area.centerx - board_w // 2
        origin_y = area.centery - board_h // 2

        shadow_rect = pygame.Rect(origin_x - 12, origin_y - 12, board_w + 24, board_h + 24)
        pygame.draw.rect(self.screen, (18, 27, 35), shadow_rect, border_radius=18)
        pygame.draw.rect(self.screen, (57, 69, 74), shadow_rect, width=1, border_radius=18)

        now = pygame.time.get_ticks()
        animation = self.animation
        progress = 1.0
        if animation:
            progress = min(1.0, (now - animation[4]) / 115)
            if progress >= 1:
                self.animation = None

        def cell_center(position: Position) -> tuple[int, int]:
            return (origin_x + position[0] * tile + tile // 2, origin_y + position[1] * tile + tile // 2)

        for y in range(row_count):
            for x in range(cols):
                pos = (x, y)
                cell = pygame.Rect(origin_x + x * tile + 2, origin_y + y * tile + 2, tile - 4, tile - 4)
                if pos in self.game.walls:
                    self._draw_wall(cell)
                else:
                    self._draw_floor(cell, (x + y) % 2 == 0)
                    if pos in self.game.goals:
                        self._draw_goal(cell.center, tile)

        boxes = set(self.game.boxes)
        player_position = self.game.player
        player_position_float = (float(player_position[0]), float(player_position[1]))
        moving_box_from = moving_box_to = None
        if animation and progress < 1:
            from_player, to_player, moving_box_from, moving_box_to, _ = animation
            player_position_float = (
                from_player[0] + (to_player[0] - from_player[0]) * progress,
                from_player[1] + (to_player[1] - from_player[1]) * progress,
            )

        for box in boxes:
            if animation and box == moving_box_to and progress < 1 and moving_box_from is not None:
                bx = moving_box_from[0] + (moving_box_to[0] - moving_box_from[0]) * progress
                by = moving_box_from[1] + (moving_box_to[1] - moving_box_from[1]) * progress
                box_center = (origin_x + bx * tile + tile / 2, origin_y + by * tile + tile / 2)
                self._draw_box(box_center, tile)
            else:
                self._draw_box(cell_center(box), tile)

        self._draw_player(
            (origin_x + player_position_float[0] * tile + tile / 2,
             origin_y + player_position_float[1] * tile + tile / 2),
            tile,
        )

    def _draw_floor(self, rect: pygame.Rect, alternate: bool) -> None:
        pygame.draw.rect(self.screen, FLOOR_ALT if alternate else FLOOR, rect, border_radius=5)
        pygame.draw.line(self.screen, (236, 230, 211), (rect.x + 7, rect.y + 5), (rect.right - 7, rect.y + 5), 1)

    def _draw_wall(self, rect: pygame.Rect) -> None:
        shadow = rect.move(0, 3)
        pygame.draw.rect(self.screen, (40, 50, 56), shadow, border_radius=6)
        pygame.draw.rect(self.screen, WALL, rect, border_radius=6)
        pygame.draw.rect(self.screen, WALL_TOP, (rect.x + 3, rect.y + 3, rect.width - 6, 7), border_radius=3)
        pygame.draw.line(self.screen, (62, 73, 80), (rect.x + 7, rect.bottom - 7), (rect.right - 7, rect.bottom - 7), 2)
        if rect.width > 40:
            pygame.draw.line(self.screen, (94, 105, 111), (rect.centerx, rect.y + 15), (rect.centerx, rect.bottom - 8), 1)

    def _draw_goal(self, center: tuple[int, int], tile: int) -> None:
        radius = max(7, int(tile * 0.21))
        pygame.draw.circle(self.screen, (191, 144, 71), center, radius + 3, 2)
        pygame.draw.circle(self.screen, GOLD, center, radius, 2)
        pygame.draw.circle(self.screen, (246, 190, 91), center, max(2, radius // 4))

    def _draw_box(self, center: tuple[float, float], tile: int) -> None:
        size = int(tile * 0.68)
        rect = pygame.Rect(0, 0, size, size)
        rect.center = (round(center[0]), round(center[1]))
        pygame.draw.rect(self.screen, (82, 48, 34), rect.move(0, 4), border_radius=7)
        pygame.draw.rect(self.screen, WOOD, rect, border_radius=7)
        pygame.draw.rect(self.screen, WOOD_LIGHT, (rect.x + 4, rect.y + 4, rect.width - 8, 5), border_radius=2)
        pygame.draw.rect(self.screen, WOOD_DARK, rect.inflate(-12, -12), width=2, border_radius=4)
        pygame.draw.line(self.screen, WOOD_LIGHT, (rect.x + 9, rect.y + 11), (rect.right - 9, rect.bottom - 11), 2)
        pygame.draw.line(self.screen, WOOD_LIGHT, (rect.right - 9, rect.y + 11), (rect.x + 9, rect.bottom - 11), 2)

    def _draw_player(self, center: tuple[float, float], tile: int) -> None:
        cx, cy = int(center[0]), int(center[1])
        radius = max(10, int(tile * 0.30))
        pygame.draw.ellipse(self.screen, (41, 55, 61), (cx - radius, cy + radius // 2, radius * 2, radius // 2))
        pygame.draw.circle(self.screen, PLAYER_DARK, (cx, cy + 2), radius)
        pygame.draw.circle(self.screen, PLAYER, (cx, cy - 1), radius - 3)
        head_radius = max(5, int(radius * 0.48))
        pygame.draw.circle(self.screen, (242, 211, 171), (cx, cy - radius // 5), head_radius)
        eye_y = cy - radius // 5
        pygame.draw.circle(self.screen, (57, 62, 61), (cx - head_radius // 3, eye_y), 1)
        pygame.draw.circle(self.screen, (57, 62, 61), (cx + head_radius // 3, eye_y), 1)
        pygame.draw.arc(self.screen, (57, 62, 61), (cx - 4, eye_y, 8, 6), math.pi * 1.05, math.pi * 1.95, 1)

    def _draw_win_overlay(self, area: pygame.Rect) -> None:
        overlay = pygame.Surface(area.size, pygame.SRCALPHA)
        overlay.fill((14, 25, 31, 175))
        self.screen.blit(overlay, area.topleft)

        has_next_level = self.game.level_index < len(self.game.levels) - 1
        card_height = 190 if has_next_level else 150
        card = pygame.Rect(0, 0, min(390, area.width - 36), card_height)
        card.center = area.center
        pygame.draw.rect(self.screen, (31, 51, 59), card, border_radius=18)
        pygame.draw.rect(self.screen, (93, 151, 127), card, width=1, border_radius=18)

        self._center_text("LEVEL COMPLETE", self.heading_font, MINT, (card.centerx, card.y + 37))
        if has_next_level:
            self._center_text("All crates are in place.", self.body_font, TEXT, (card.centerx, card.y + 73))
            next_rect = pygame.Rect(card.x + 58, card.y + 112, card.width - 116, 42)
            self._draw_button(next_rect, "Next Level   →", True, False, primary=True)
            self.popup_button = Button(next_rect, "Next Level", "next", primary=True)
        else:
            self._center_text("You solved every puzzle!", self.body_font, TEXT, (card.centerx, card.y + 75))
            self._center_text("Choose a level to play again", self.small_font, MUTED, (card.centerx, card.y + 105))

    def _draw_sidebar(self, rect: pygame.Rect) -> None:
        self._panel(rect)
        pad = 22
        x = rect.x + pad
        y = rect.y + 22
        self._text("YOUR SESSION", self.small_font, MINT, (x, y))
        y += 30

        stat_w = (rect.width - pad * 2 - 10) // 2
        self._stat_card(pygame.Rect(x, y, stat_w, 82), "MOVES", str(self.game.moves))
        self._stat_card(pygame.Rect(x + stat_w + 10, y, stat_w, 82), "CRATES", f"{self.game.boxes_on_goals}/{len(self.game.goals)}")
        y += 103

        self._text("LEVEL SELECT", self.small_font, MUTED, (x, y))
        y += 24
        self.buttons = []
        card_gap = 8
        card_h = 52
        for index, level in enumerate(self.game.levels):
            card = pygame.Rect(x, y, rect.width - pad * 2, card_h)
            active = index == self.game.level_index
            pygame.draw.rect(self.screen, (41, 67, 70) if active else BG_SOFT, card, border_radius=9)
            pygame.draw.rect(self.screen, MINT_DARK if active else PANEL_BORDER, card, width=1, border_radius=9)
            self._text(f"{index + 1:02d}", self.heading_font, MINT if active else MUTED, (card.x + 12, card.y + 14))
            name = self.body_font.render(level.name, True, TEXT if active else MUTED)
            self.screen.blit(name, (card.x + 53, card.y + 17))
            self.buttons.append(Button(card, level.name, f"level:{index}"))
            y += card_h + card_gap

        y += 7
        self._text("ACTIONS", self.small_font, MUTED, (x, y))
        y += 22
        button_gap = 8
        button_h = 39
        half = (rect.width - pad * 2 - button_gap) // 2
        undo_rect = pygame.Rect(x, y, half, button_h)
        restart_rect = pygame.Rect(x + half + button_gap, y, half, button_h)
        self._draw_button(undo_rect, "↶  Undo", False, True)
        self._draw_button(restart_rect, "↻  Restart", False, True)
        self.buttons.extend([Button(undo_rect, "Undo", "undo"), Button(restart_rect, "Restart", "restart")])
        y += button_h + 8

        next_rect = pygame.Rect(x, y, rect.width - pad * 2, 42)
        can_advance = self.game.is_won and self.game.level_index < len(self.game.levels) - 1
        self._draw_button(next_rect, "Next level   →", can_advance, False, primary=True)
        self.buttons.append(Button(next_rect, "Next level", "next", enabled=can_advance, primary=True))
        y += 58

        self._text("CONTROLS", self.small_font, MUTED, (x, y))
        y += 22
        self._key_hint(x, y, "↑ ↓ ← →", "Move")
        self._key_hint(x, y + 25, "W A S D", "Move")
        self._key_hint(x, y + 50, "Z / BACKSPACE", "Undo")
        self._key_hint(x, y + 75, "R", "Restart")
        self._key_hint(x, y + 100, "N", "Next level")

    def _stat_card(self, rect: pygame.Rect, label: str, value: str) -> None:
        pygame.draw.rect(self.screen, BG_SOFT, rect, border_radius=10)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, width=1, border_radius=10)
        self._text(label, self.small_font, MUTED, (rect.x + 12, rect.y + 12))
        self._text(value, self.number_font, TEXT, (rect.x + 12, rect.y + 35))

    def _draw_button(self, rect: pygame.Rect, label: str, enabled: bool, secondary: bool, primary: bool = False) -> None:
        if not enabled:
            fill, border, color = (39, 51, 61), (51, 65, 76), (109, 126, 137)
        elif primary:
            fill, border, color = MINT_DARK, MINT, (250, 255, 250)
        elif secondary:
            fill, border, color = PANEL_LIGHT, PANEL_BORDER, TEXT
        else:
            fill, border, color = PANEL_LIGHT, PANEL_BORDER, TEXT
        pygame.draw.rect(self.screen, fill, rect, border_radius=9)
        pygame.draw.rect(self.screen, border, rect, width=1, border_radius=9)
        self._center_text(label, self.body_font, color, rect.center)

    def _key_hint(self, x: int, y: int, key: str, description: str) -> None:
        key_surface = self.small_font.render(key, True, MINT)
        desc_surface = self.small_font.render(description, True, MUTED)
        self.screen.blit(key_surface, (x, y))
        self.screen.blit(desc_surface, (x + 125, y))

    def _draw_toast(self, width: int, height: int) -> None:
        if pygame.time.get_ticks() > self.toast_until or not self.toast:
            return
        label = self.body_font.render(self.toast, True, TEXT)
        rect = pygame.Rect(0, 0, label.get_width() + 34, 42)
        rect.center = (width // 2, height - 25)
        pygame.draw.rect(self.screen, (38, 57, 65), rect, border_radius=12)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, width=1, border_radius=12)
        self.screen.blit(label, label.get_rect(center=rect.center))

    def _panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (12, 19, 27), rect.move(0, 5), border_radius=17)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=17)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, width=1, border_radius=17)

    def _text(self, value: str, font: pygame.font.Font, color: tuple[int, int, int], position: tuple[int, int]) -> None:
        self.screen.blit(font.render(value, True, color), position)

    def _center_text(self, value: str, font: pygame.font.Font, color: tuple[int, int, int], center: tuple[int, int]) -> None:
        surface = font.render(value, True, color)
        self.screen.blit(surface, surface.get_rect(center=center))


def main() -> None:
    parser = argparse.ArgumentParser(description="Play Sokoban with a graphical interface.")
    parser.add_argument("--level", type=int, default=1, help="starting level number (default: 1)")
    args = parser.parse_args()
    if not 1 <= args.level <= len(LEVELS):
        parser.error(f"--level must be between 1 and {len(LEVELS)}")
    SokobanApp(start_level=args.level - 1).run()


if __name__ == "__main__":
    main()
