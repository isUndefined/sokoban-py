"""Isometric 2.5D Pygame interface for Sokoban."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from sokoban import Game, LEVELS, Position


WIDTH, HEIGHT = 1280, 860
FPS = 60

BG = (12, 18, 32)
PANEL = (22, 31, 52)
PANEL_HI = (31, 43, 69)
PANEL_EDGE = (69, 82, 125)
TEXT = (239, 241, 255)
MUTED = (155, 168, 203)
GOLD = (255, 190, 75)
MINT = (93, 239, 157)
MINT_DARK = (33, 153, 91)


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str
    enabled: bool = True
    primary: bool = False


@dataclass
class MoveAnimation:
    start: Position
    end: Position
    direction_row: int
    started_at: int
    box_start: Position | None = None
    box_end: Position | None = None
    duration: int = 210


class SokobanApp:
    def __init__(self, start_level: int = 0) -> None:
        pygame.init()
        pygame.display.set_caption("Sokoban — The Lost Warehouse")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("dejavusans", 31, bold=True)
        self.heading_font = pygame.font.SysFont("dejavusans", 19, bold=True)
        self.body_font = pygame.font.SysFont("dejavusans", 15)
        self.small_font = pygame.font.SysFont("dejavusans", 12)
        self.number_font = pygame.font.SysFont("dejavusans", 28, bold=True)
        self.hero_sheet = self._load_hero_sheet()
        self.hero_frames = self._slice_hero_sheet()
        self.game = Game(level_index=start_level)
        self.buttons: list[Button] = []
        self.popup_button: Button | None = None
        self.running = True
        self.animation: MoveAnimation | None = None
        self.facing_row = 0
        self.toast = ""
        self.toast_until = 0
        self.particles: list[tuple[float, float, float, float, int]] = []
        self.particle_origin = (0, 0)
        # Match repeat timing to the 210 ms four-frame movement animation.
        pygame.key.set_repeat(210, 210)

    def _load_hero_sheet(self) -> pygame.Surface:
        asset = Path(__file__).parent / "assets" / "hero_walk.webp"
        try:
            return pygame.image.load(str(asset)).convert_alpha()
        except (pygame.error, FileNotFoundError) as exc:
            raise RuntimeError(
                f"Could not load character spritesheet: {asset}. "
                "Make sure the assets directory is included in the project."
            ) from exc

    def _slice_hero_sheet(self) -> list[list[pygame.Surface]]:
        sheet_w, sheet_h = self.hero_sheet.get_size()
        if sheet_w % 4 or sheet_h % 4:
            raise RuntimeError("The hero spritesheet must be a regular 4x4 grid.")

        frame_w, frame_h = sheet_w // 4, sheet_h // 4
        frames: list[list[pygame.Surface]] = []
        for row in range(4):
            direction: list[pygame.Surface] = []
            for col in range(4):
                frame = pygame.Rect(col * frame_w, row * frame_h, frame_w, frame_h)
                direction.append(self.hero_sheet.subsurface(frame).copy())
            frames.append(direction)
        return frames

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
                self._handle_key(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _handle_key(self, event: pygame.event.Event) -> None:
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
        elif event.key == pygame.K_r or char == "к":
            self._restart()
        elif event.key == pygame.K_n or char in ("n", "т"):
            self._next_level()

    def _move(self, dx: int, dy: int) -> None:
        if self.game.is_won:
            return
        old_player = self.game.player
        old_boxes = set(self.game.boxes)
        if not self.game.move(dx, dy):
            self._show_toast("That way is blocked")
            return

        new_boxes = set(self.game.boxes)
        box_start = next(iter(old_boxes - new_boxes), None)
        box_end = next(iter(new_boxes - old_boxes), None)
        direction_row = self._direction_row(dx, dy)
        self.facing_row = direction_row
        self.animation = MoveAnimation(
            old_player,
            self.game.player,
            direction_row,
            pygame.time.get_ticks(),
            box_start,
            box_end,
        )
        if self.game.is_won:
            self._spawn_win_particles()

    @staticmethod
    def _direction_row(dx: int, dy: int) -> int:
        # Sprite-sheet rows: front-facing, back-facing, left-facing, right-facing.
        if dy > 0:
            return 0
        if dy < 0:
            return 1
        if dx < 0:
            return 2
        return 3

    def _undo(self) -> None:
        if self.game.undo():
            self.animation = None
            self._show_toast("Move undone")
        else:
            self._show_toast("Nothing to undo")

    def _restart(self) -> None:
        self.game.restart()
        self.animation = None
        self.particles.clear()
        self._show_toast("Level restarted")

    def _next_level(self) -> None:
        if not self.game.is_won:
            self._show_toast("Complete the level first")
        elif not self.game.next_level():
            self._show_toast("You solved every puzzle!")
        else:
            self.animation = None
            self.particles.clear()
            self.facing_row = 0
            self._show_toast(f"Level {self.game.level_index + 1}: {self.game.level.name}")

    def _select_level(self, index: int) -> None:
        if 0 <= index < len(self.game.levels):
            self.game = Game(levels=self.game.levels, level_index=index)
            self.animation = None
            self.particles.clear()
            self._show_toast(f"Level {index + 1} selected")

    def _show_toast(self, message: str) -> None:
        self.toast = message
        self.toast_until = pygame.time.get_ticks() + 1500

    def _board_area(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        margin, top, gap = 28, 108, 20
        side_width = min(310, max(278, int(width * 0.265)))
        board_width = width - margin * 2 - gap - side_width
        panel_height = max(520, height - top - 26)
        board_rect = pygame.Rect(margin, top, board_width, panel_height)
        return pygame.Rect(board_rect.x + 14, board_rect.y + 78, board_rect.width - 28, board_rect.height - 92)

    def _spawn_win_particles(self) -> None:
        now = pygame.time.get_ticks()
        self.particle_origin = self._board_area().center
        self.particles = []
        for index in range(42):
            angle = math.tau * index / 42
            speed = 35 + (index % 6) * 11
            self.particles.append((0.0, 0.0, math.cos(angle) * speed, math.sin(angle) * speed, now))

    def _handle_click(self, pos: tuple[int, int]) -> None:
        if self.popup_button and self.popup_button.enabled and self.popup_button.rect.collidepoint(pos):
            self._next_level()
            return
        for button in self.buttons:
            if button.enabled and button.rect.collidepoint(pos):
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
        width, height = self.screen.get_size()
        self.screen.fill(BG)
        self._draw_background(width, height)
        self._draw_header(width)

        margin = 28
        top = 108
        gap = 20
        side_width = min(310, max(278, int(width * 0.265)))
        board_width = width - margin * 2 - gap - side_width
        panel_height = max(520, height - top - 26)
        board_rect = pygame.Rect(margin, top, board_width, panel_height)
        side_rect = pygame.Rect(board_rect.right + gap, top, side_width, panel_height)

        self._draw_board_panel(board_rect)
        self._draw_sidebar(side_rect)
        self._draw_toast(width, height)

    def _draw_background(self, width: int, height: int) -> None:
        for x in range(0, width, 54):
            pygame.draw.line(self.screen, (17, 25, 43), (x, 0), (x, height), 1)
        for y in range(0, height, 54):
            pygame.draw.line(self.screen, (17, 25, 43), (0, y), (width, y), 1)
        self._glow((width - 70, 50), 210, (57, 74, 160), 32)
        self._glow((65, height - 40), 190, (161, 88, 43), 26)
        self._text("✦", self.heading_font, (92, 112, 190), (width - 240, 124))
        self._text("✧", self.body_font, (133, 110, 177), (width - 130, height - 120))

    def _draw_header(self, width: int) -> None:
        self._text("SOKOBAN", self.title_font, TEXT, (30, 18))
        self._text("THE LOST WAREHOUSE", self.small_font, (119, 224, 189), (34, 58))
        tagline = "PUSH  ·  PLAN  ·  SOLVE"
        tag = self.body_font.render(tagline, True, MUTED)
        self.screen.blit(tag, (width - tag.get_width() - 32, 38))
        pygame.draw.line(self.screen, (49, 62, 96), (28, 88), (width - 28, 88), 1)

    def _draw_board_panel(self, rect: pygame.Rect) -> None:
        self._panel(rect)
        self._text(f"LEVEL {self.game.level_index + 1:02d}", self.small_font, (117, 229, 188), (rect.x + 24, rect.y + 18))
        self._text(self.game.level.name, self.heading_font, TEXT, (rect.x + 24, rect.y + 42))
        board_area = pygame.Rect(rect.x + 14, rect.y + 78, rect.width - 28, rect.height - 92)
        self._draw_isometric_board(board_area)
        self._update_particles()
        if self.game.is_won:
            self._draw_win_overlay(board_area)

    def _draw_isometric_board(self, area: pygame.Rect) -> None:
        rows = self.game.level.rows
        cols, row_count = len(rows[0]), len(rows)
        tile_w = min(78, int((area.width - 65) * 2 / (cols + row_count)))
        tile_w = max(58, tile_w)
        tile_h = int(tile_w * 0.48)
        wall_h = int(tile_h * 0.78)

        origin_x = area.centerx - (cols - row_count) * tile_w / 4
        origin_y = area.centery - (cols + row_count - 2) * tile_h / 4

        def project(pos: tuple[float, float]) -> tuple[int, int]:
            gx, gy = pos
            return (
                round(origin_x + (gx - gy) * tile_w / 2),
                round(origin_y + (gx + gy) * tile_h / 2),
            )

        for y in range(row_count):
            for x in range(cols):
                center = project((x, y))
                self._draw_floor_tile(center, tile_w, tile_h, (x + y) % 2 == 0)
                if (x, y) in self.game.goals:
                    self._draw_goal(center, tile_w, tile_h)

        now = pygame.time.get_ticks()
        animation = self.animation
        progress = 1.0
        if animation:
            progress = min(1.0, (now - animation.started_at) / animation.duration)
            if progress >= 1.0:
                self.animation = None

        animated_box_pos: tuple[float, float] | None = None
        if animation and animation.box_start and animation.box_end and progress < 1:
            eased = self._ease(progress)
            animated_box_pos = (
                animation.box_start[0] + (animation.box_end[0] - animation.box_start[0]) * eased,
                animation.box_start[1] + (animation.box_end[1] - animation.box_start[1]) * eased,
            )

        hero_pos: tuple[float, float] = self.game.player
        hero_row = self.facing_row
        moving = bool(animation and progress < 1)
        if animation and moving:
            eased = self._ease(progress)
            hero_pos = (
                animation.start[0] + (animation.end[0] - animation.start[0]) * eased,
                animation.start[1] + (animation.end[1] - animation.start[1]) * eased,
            )
            hero_row = animation.direction_row

        drawables: list[tuple[float, int, float, float, str, Position | None]] = []
        for y in range(row_count):
            for x in range(cols):
                pos = (x, y)
                if pos in self.game.walls:
                    drawables.append((x + y, 0, x, y, "wall", pos))
                elif pos in self.game.boxes and not (animation and pos == animation.box_end and animated_box_pos):
                    drawables.append((x + y, 1, x, y, "box", pos))

        if animation and animation.box_start and animated_box_pos and progress < 1:
            bx, by = animated_box_pos
            drawables.append((bx + by, 1, bx, by, "moving_box", None))
        drawables.append((hero_pos[0] + hero_pos[1], 2, hero_pos[0], hero_pos[1], "hero", None))

        for _, _, gx, gy, kind, pos in sorted(drawables, key=lambda item: (item[0], item[1])):
            if kind == "wall" and pos is not None:
                self._draw_stone_block(project(pos), tile_w, tile_h, wall_h, pos[0], pos[1])
            elif kind == "box" and pos is not None:
                self._draw_crate(project(pos), tile_w, tile_h)
            elif kind == "moving_box":
                self._draw_crate(project((gx, gy)), tile_w, tile_h)
            elif kind == "hero":
                started_at = animation.started_at if moving and animation else None
                self._draw_hero(project((gx, gy)), hero_row, moving, now, tile_h, started_at)

    @staticmethod
    def _ease(value: float) -> float:
        return value * value * (3 - 2 * value)

    def _draw_floor_tile(self, center: tuple[int, int], tile_w: int, tile_h: int, alternate: bool) -> None:
        cx, cy = center
        hw, hh = tile_w // 2, tile_h // 2
        points = [(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)]
        color = (50, 59, 82) if alternate else (43, 52, 74)
        pygame.draw.polygon(self.screen, (23, 30, 50), [(x, y + 4) for x, y in points])
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, (76, 88, 118), points, width=1)
        pygame.draw.line(self.screen, (69, 81, 111), (cx - hw + 7, cy), (cx, cy - hh + 4), 1)

    def _draw_stone_block(self, ground: tuple[int, int], tile_w: int, tile_h: int, wall_h: int, x: int, y: int) -> None:
        cx, cy = ground
        hw, hh = tile_w // 2, tile_h // 2
        top_y = cy - wall_h
        top = [(cx, top_y - hh), (cx + hw, top_y), (cx, top_y + hh), (cx - hw, top_y)]
        left_face = [top[3], top[2], (cx, cy + hh), (cx - hw, cy)]
        right_face = [top[2], top[1], (cx + hw, cy), (cx, cy + hh)]
        pygame.draw.polygon(self.screen, (57, 64, 91), left_face)
        pygame.draw.polygon(self.screen, (43, 49, 74), right_face)
        pygame.draw.polygon(self.screen, (106, 116, 151), top)
        pygame.draw.polygon(self.screen, (138, 146, 177), top, width=1)
        seam = (cx + (x % 2) * 7 - 4, top_y + 1)
        pygame.draw.line(self.screen, (83, 92, 126), (seam[0] - 8, seam[1] - 2), (seam[0] + 8, seam[1] + 2), 2)
        pygame.draw.line(self.screen, (153, 160, 185), (cx - hw + 8, top_y - 3), (cx - 4, top_y - hh + 4), 2)

    def _draw_goal(self, center: tuple[int, int], tile_w: int, tile_h: int) -> None:
        cx, cy = center
        self._glow((cx, cy), max(28, tile_w // 2), (67, 235, 149), 48)
        radius = max(8, int(tile_w * 0.17))
        pygame.draw.ellipse(self.screen, (28, 108, 83), (cx - radius - 4, cy - radius // 2 - 3, (radius + 4) * 2, radius + 7))
        pygame.draw.ellipse(self.screen, (70, 248, 157), (cx - radius, cy - radius // 2, radius * 2, radius), width=3)
        pygame.draw.ellipse(self.screen, (154, 255, 188), (cx - radius // 2, cy - radius // 4, radius, max(4, radius // 2)), width=2)
        pygame.draw.circle(self.screen, (205, 255, 207), (cx, cy), 2)

    def _draw_crate(self, ground: tuple[int, int], tile_w: int, tile_h: int) -> None:
        cx, cy = ground
        size_w = int(tile_w * 0.52)
        size_h = int(tile_h * 0.72)
        lift = int(tile_h * 0.92)
        top_cy = cy - lift
        hw, hh = size_w // 2, size_h // 2
        top = [(cx, top_cy - hh), (cx + hw, top_cy), (cx, top_cy + hh), (cx - hw, top_cy)]
        bottom_left = (cx - hw, top_cy + lift)
        bottom_front = (cx, top_cy + hh + lift)
        bottom_right = (cx + hw, top_cy + lift)
        side_left = [top[3], top[2], bottom_front, bottom_left]
        side_right = [top[2], top[1], bottom_right, bottom_front]
        pygame.draw.ellipse(self.screen, (13, 17, 29), (cx - hw, cy - 5, size_w, max(12, tile_h // 2)))
        pygame.draw.polygon(self.screen, (116, 64, 42), side_left)
        pygame.draw.polygon(self.screen, (83, 48, 39), side_right)
        pygame.draw.polygon(self.screen, (199, 127, 71), top)
        pygame.draw.polygon(self.screen, (242, 178, 112), top, width=2)
        pygame.draw.line(self.screen, (242, 178, 112), top[3], top[1], 3)
        pygame.draw.line(self.screen, (145, 79, 46), top[0], top[2], 3)
        pygame.draw.line(self.screen, (226, 157, 93), side_left[0], bottom_front, 2)
        pygame.draw.line(self.screen, (226, 157, 93), side_right[1], bottom_front, 2)
        pygame.draw.polygon(self.screen, (101, 58, 39), [
            (cx - hw + 7, top_cy + lift // 2),
            (cx, top_cy + hh + lift // 2),
            (cx, bottom_front[1] - 5),
            (cx - hw + 7, bottom_left[1] - 5),
        ], width=2)

    def _draw_hero(
        self,
        ground: tuple[int, int],
        direction_row: int,
        moving: bool,
        now: int,
        tile_h: int,
        animation_started_at: int | None = None,
    ) -> None:
        frame_index = min(3, (now - animation_started_at) // 52) if moving and animation_started_at is not None else 0
        sprite = self.hero_frames[direction_row][frame_index]
        target_h = int(tile_h * 3.45)
        target_w = int(target_h * 96 / 144)
        sprite = pygame.transform.smoothscale(sprite, (target_w, target_h))
        shadow_y = ground[1] + int(tile_h * 0.16)
        pygame.draw.ellipse(
            self.screen,
            (12, 16, 29),
            (ground[0] - target_w // 4, shadow_y - 5, target_w // 2, max(9, tile_h // 2)),
        )
        idle_bob = 0 if moving else round(math.sin(now / 390) * 2)
        rect = sprite.get_rect(midbottom=(ground[0], shadow_y + 6 + idle_bob))
        self.screen.blit(sprite, rect)

    def _draw_win_overlay(self, area: pygame.Rect) -> None:
        overlay = pygame.Surface(area.size, pygame.SRCALPHA)
        overlay.fill((7, 12, 27, 190))
        self.screen.blit(overlay, area.topleft)
        has_next = self.game.level_index < len(self.game.levels) - 1
        card_w = min(430, area.width - 38)
        card_h = 240 if has_next else 205
        card = pygame.Rect(0, 0, card_w, card_h)
        card.center = area.center
        pygame.draw.rect(self.screen, (13, 22, 45), card.move(0, 8), border_radius=23)
        pygame.draw.rect(self.screen, (26, 38, 69), card, border_radius=23)
        pygame.draw.rect(self.screen, (109, 130, 196), card, width=2, border_radius=23)
        self._draw_star((card.centerx - 90, card.y + 22), 19, GOLD)
        self._draw_star((card.centerx, card.y + 9), 27, (255, 215, 104))
        self._draw_star((card.centerx + 90, card.y + 22), 19, GOLD)
        self._center_text("LEVEL COMPLETE!", self.heading_font, (255, 216, 126), (card.centerx, card.y + 75))
        if has_next:
            self._center_text("All crates are in place.", self.body_font, TEXT, (card.centerx, card.y + 108))
            self._center_text(f"Solved in {self.game.moves} moves", self.small_font, MUTED, (card.centerx, card.y + 133))
            button_rect = pygame.Rect(card.x + 64, card.y + 160, card.width - 128, 52)
            self._draw_button(button_rect, "▶   NEXT LEVEL", True, False, primary=True)
            self.popup_button = Button(button_rect, "Next level", "next", primary=True)
        else:
            self._center_text("You solved every puzzle!", self.body_font, TEXT, (card.centerx, card.y + 112))
            self._center_text("Pick any level to play again", self.small_font, MUTED, (card.centerx, card.y + 141))

    def _draw_star(self, center: tuple[int, int], radius: int, color: tuple[int, int, int]) -> None:
        points = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            r = radius if i % 2 == 0 else radius * 0.46
            points.append((round(center[0] + math.cos(angle) * r), round(center[1] + math.sin(angle) * r)))
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, (255, 239, 178), points, width=2)

    def _draw_sidebar(self, rect: pygame.Rect) -> None:
        self._panel(rect)
        pad = 20
        x = rect.x + pad
        y = rect.y + 22
        self._text("YOUR ADVENTURE", self.small_font, (128, 231, 195), (x, y))
        y += 31

        stat_gap = 9
        stat_w = (rect.width - pad * 2 - stat_gap) // 2
        self._stat_card(pygame.Rect(x, y, stat_w, 82), "MOVES", str(self.game.moves))
        self._stat_card(pygame.Rect(x + stat_w + stat_gap, y, stat_w, 82), "CRATES", f"{self.game.boxes_on_goals}/{len(self.game.goals)}")
        y += 101

        self._text("CHOOSE A LEVEL", self.small_font, MUTED, (x, y))
        y += 24
        self.buttons = []
        for index, level in enumerate(self.game.levels):
            card = pygame.Rect(x, y, rect.width - pad * 2, 46)
            active = index == self.game.level_index
            pygame.draw.rect(self.screen, (36, 74, 77) if active else (18, 27, 48), card, border_radius=10)
            pygame.draw.rect(self.screen, (70, 177, 145) if active else (55, 70, 105), card, width=1, border_radius=10)
            self._text(f"{index + 1:02d}", self.body_font, (128, 235, 190) if active else MUTED, (card.x + 13, card.y + 14))
            self._text(level.name, self.body_font, TEXT if active else MUTED, (card.x + 54, card.y + 14))
            self.buttons.append(Button(card, level.name, f"level:{index}"))
            y += 53

        y += 6
        self._text("QUICK ACTIONS", self.small_font, MUTED, (x, y))
        y += 22
        button_gap = 8
        half = (rect.width - pad * 2 - button_gap) // 2
        undo_rect = pygame.Rect(x, y, half, 42)
        restart_rect = pygame.Rect(x + half + button_gap, y, half, 42)
        self._draw_button(undo_rect, "↶  UNDO", True, True)
        self._draw_button(restart_rect, "⟳  RESTART", True, True)
        self.buttons.extend([Button(undo_rect, "Undo", "undo"), Button(restart_rect, "Restart", "restart")])
        y += 58

        next_rect = pygame.Rect(x, y, rect.width - pad * 2, 44)
        can_advance = self.game.is_won and self.game.level_index < len(self.game.levels) - 1
        self._draw_button(next_rect, "NEXT LEVEL   →", can_advance, False, primary=True)
        self.buttons.append(Button(next_rect, "Next Level", "next", enabled=can_advance, primary=True))
        y += 63

        self._text("CONTROLS", self.small_font, MUTED, (x, y))
        y += 22
        self._key_hint(x, y, "↑ ↓ ← →", "Move")
        self._key_hint(x, y + 22, "W A S D", "Move")
        self._key_hint(x, y + 44, "Z / BACKSPACE", "Undo")
        self._key_hint(x, y + 66, "R", "Restart")
        self._key_hint(x, y + 88, "N", "Next level")

        progress_rect = pygame.Rect(x, rect.bottom - 49, rect.width - pad * 2, 7)
        pygame.draw.rect(self.screen, (43, 53, 83), progress_rect, border_radius=4)
        progress = (self.game.level_index + 1) / len(self.game.levels)
        fill_rect = progress_rect.copy()
        fill_rect.width = max(7, int(progress_rect.width * progress))
        pygame.draw.rect(self.screen, (73, 205, 140), fill_rect, border_radius=4)

    def _stat_card(self, rect: pygame.Rect, label: str, value: str) -> None:
        pygame.draw.rect(self.screen, (17, 26, 47), rect, border_radius=12)
        pygame.draw.rect(self.screen, (55, 69, 104), rect, width=1, border_radius=12)
        self._text(label, self.small_font, MUTED, (rect.x + 12, rect.y + 11))
        self._text(value, self.number_font, TEXT, (rect.x + 12, rect.y + 35))

    def _draw_button(
        self,
        rect: pygame.Rect,
        label: str,
        enabled: bool,
        secondary: bool,
        primary: bool = False,
    ) -> None:
        hovered = enabled and rect.collidepoint(pygame.mouse.get_pos())
        if not enabled:
            fill, border, color = (34, 42, 62), (52, 62, 91), (100, 111, 145)
        elif primary:
            fill, border, color = ((48, 190, 104) if hovered else (31, 151, 83)), (111, 244, 157), (255, 255, 246)
        elif secondary:
            fill, border, color = ((53, 66, 99) if hovered else (35, 46, 76)), (81, 96, 138), TEXT
        else:
            fill, border, color = ((53, 66, 99) if hovered else (35, 46, 76)), (81, 96, 138), TEXT
        pygame.draw.rect(self.screen, (9, 14, 29), rect.move(0, 3), border_radius=10)
        pygame.draw.rect(self.screen, fill, rect, border_radius=10)
        pygame.draw.rect(self.screen, border, rect, width=1, border_radius=10)
        self._center_text(label, self.body_font, color, rect.center)

    def _key_hint(self, x: int, y: int, key: str, description: str) -> None:
        self._text(key, self.small_font, (128, 231, 195), (x, y))
        self._text(description, self.small_font, MUTED, (x + 130, y))

    def _draw_toast(self, width: int, height: int) -> None:
        if pygame.time.get_ticks() > self.toast_until or not self.toast:
            return
        label = self.body_font.render(self.toast, True, TEXT)
        rect = pygame.Rect(0, 0, label.get_width() + 36, 44)
        rect.center = (width // 2, height - 25)
        pygame.draw.rect(self.screen, (29, 42, 71), rect, border_radius=12)
        pygame.draw.rect(self.screen, (79, 97, 147), rect, width=1, border_radius=12)
        self.screen.blit(label, label.get_rect(center=rect.center))

    def _update_particles(self) -> None:
        if not self.particles:
            return
        now = pygame.time.get_ticks()
        alive = []
        for x0, y0, vx, vy, start in self.particles:
            age = (now - start) / 1000
            if age > 1.1:
                continue
            alive.append((x0, y0, vx, vy, start))
            x = x0 + vx * age
            y = y0 + vy * age + 34 * age * age
            radius = max(1, int(4 * (1 - age)))
            color = (255, int(190 + 55 * (1 - age)), 95)
            pygame.draw.circle(
                self.screen,
                color,
                (int(self.particle_origin[0] + x), int(self.particle_origin[1] + y)),
                radius,
            )
        self.particles = alive

    def _glow(self, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> None:
        diameter = radius * 2
        layer = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        for factor in (1.0, 0.72, 0.42, 0.2):
            r = max(1, int(radius * factor))
            a = max(1, int(alpha * (1 - factor * 0.42)))
            pygame.draw.circle(layer, (*color, a), (radius, radius), r)
        self.screen.blit(layer, (center[0] - radius, center[1] - radius), special_flags=pygame.BLEND_RGBA_ADD)

    def _panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (5, 9, 20), rect.move(0, 5), border_radius=20)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=20)
        pygame.draw.rect(self.screen, PANEL_EDGE, rect, width=1, border_radius=20)

    def _text(self, value: str, font: pygame.font.Font, color: tuple[int, int, int], position: tuple[int, int]) -> None:
        self.screen.blit(font.render(value, True, color), position)

    def _center_text(self, value: str, font: pygame.font.Font, color: tuple[int, int, int], center: tuple[int, int]) -> None:
        surface = font.render(value, True, color)
        self.screen.blit(surface, surface.get_rect(center=center))


def main() -> None:
    parser = argparse.ArgumentParser(description="Play Sokoban with an animated 2.5D graphical interface.")
    parser.add_argument("--level", type=int, default=1, help="starting level number (default: 1)")
    args = parser.parse_args()
    if not 1 <= args.level <= len(LEVELS):
        parser.error(f"--level must be between 1 and {len(LEVELS)}")
    SokobanApp(start_level=args.level - 1).run()


if __name__ == "__main__":
    main()
