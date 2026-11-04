"""Fixed-layout, top-down Sokoban UI inspired by the approved 2D screen.

The game logic still lives entirely in ``sokoban.Game``. Presentation uses five consistent, transparent sprites prepared from the
approved design reference; no isometric or perspective renderer.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pygame

from sokoban import Game, LEVELS

DESIGN_W, DESIGN_H = 1536, 1024
FPS = 60
MOVE_MS = 180
GAME_TILE_SIZE = 78  # Fixed logical pixels in the 1536x1024 design canvas
GOAL_GLOW_MS = 240
VICTORY_REVEAL_MS = 280

# Input is driven by physical press/release state instead of SDL key repeat.
# This keeps held movement synchronized with the 180ms tile animation.
DIRECTION_KEYS = {
    pygame.K_UP: (0, -1), pygame.K_w: (0, -1),
    pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1),
    pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0),
    pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0),
}
DIRECTION_CHARS = {
    "ц": (0, -1), "ы": (0, 1),
    "ф": (-1, 0), "в": (1, 0),
}
ASSETS = Path(__file__).resolve().parent / "assets" / "flat"
BG_TOP = (12, 29, 54)
BG_BOTTOM = (8, 24, 48)
WHITE = (244, 248, 255)
MUTED = (169, 187, 217)
ACCENT = (255, 188, 45)
BLUE = (60, 100, 156)
GREEN = (68, 194, 98)
FLOOR_GROUT = (200, 177, 152)
FLOOR_TILE = (241, 223, 201)
FLOOR_HIGHLIGHT = (251, 237, 218)


@dataclass
class Button:
    rect: pygame.Rect
    action: str
    enabled: bool = True


@dataclass
class MoveAnimation:
    source: tuple[int, int]
    target: tuple[int, int]
    start: int
    box_source: tuple[int, int] | None = None
    box_target: tuple[int, int] | None = None


@dataclass
class GoalGlow:
    position: tuple[int, int]
    start: int  # When the crate finishes moving into its target.


class FlatSokobanApp:
    """A fixed virtual-canvas GUI that scales without rearranging the UI."""

    def __init__(self, start_level: int = 0) -> None:
        pygame.init()
        pygame.display.set_caption("Sokoban")
        self.screen = pygame.display.set_mode((1280, 854), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.canvas = pygame.Surface((DESIGN_W, DESIGN_H)).convert()
        self.background = self._make_background()
        self.assets = self._load_assets()
        self.scale_cache: dict[tuple[str, int], pygame.Surface] = {}
        self.facing = "up"  # sprite direction, never rotate a top-down character
        # One font family and one text hierarchy across HUD, buttons, and menus.
        ui_font = "liberationsans"
        self.fonts = {
            "brand": pygame.font.SysFont(ui_font, 49, bold=True),
            "big": pygame.font.SysFont(ui_font, 32, bold=True),
            "medium": pygame.font.SysFont(ui_font, 27, bold=True),
            "small": pygame.font.SysFont(ui_font, 22),
            "mini": pygame.font.SysFont(ui_font, 19),
        }
        self.game = Game(level_index=start_level)
        self.running = True
        self.buttons: list[Button] = []
        self.menu_open = False
        self.animation: MoveAnimation | None = None
        self.goal_glow: GoalGlow | None = None
        self.victory_started_at: int | None = None
        self._held_directions: dict[int, tuple[int, int]] = {}
        self._queued_direction: tuple[int, int] | None = None
        self._layout = (0.0, 0.0, 1.0)
        self._board = (0, 0, 0)
        self.toast = ""
        self.toast_until = 0
        pygame.key.set_repeat()  # Disable OS-repeat, which drops events mid-animation.

    def _load_assets(self) -> dict[str, pygame.Surface]:
        """Load the approved atlas plus four independently oriented character views."""
        path = ASSETS / "atlas.png"
        names = ("floor", "wall", "crate", "goal", "player_up")
        try:
            atlas = pygame.image.load(str(path)).convert_alpha()
        except (OSError, pygame.error) as exc:
            raise RuntimeError(f"Missing 2D sprite atlas: {path}") from exc
        cell = 128
        expected = (cell * len(names), cell)
        if atlas.get_size() != expected:
            raise RuntimeError(f"Sprite atlas must be {expected}, got {atlas.get_size()}")
        assets = {
            name: atlas.subsurface(pygame.Rect(i * cell, 0, cell, cell)).copy()
            for i, name in enumerate(names)
        }
        # Normalize the visible object inside the fixed 128x128 source cell.
        # Do this once, not by adding per-sprite offsets to board coordinates.
        for name in ("crate", "goal"):
            sprite = assets[name]
            bounds = sprite.get_bounding_rect(min_alpha=16)
            if bounds.width and bounds.height:
                normalized = pygame.Surface((cell, cell), pygame.SRCALPHA)
                normalized.blit(sprite, ((cell - bounds.width) // 2 - bounds.x,
                                         (cell - bounds.height) // 2 - bounds.y))
                assets[name] = normalized

        for direction in ("up", "down", "left", "right"):
            path = ASSETS / f"player_{direction}.png"
            try:
                sprite = pygame.image.load(str(path)).convert_alpha()
            except (OSError, pygame.error) as exc:
                raise RuntimeError(f"Missing directional player sprite: {path}") from exc
            if sprite.get_size() != (cell, cell):
                raise RuntimeError(f"Player sprite {path} must be {cell}x{cell}")
            assets[f"player_{direction}"] = sprite

        # Approved 16-frame walking sprite sheet, 4 directions by 4 phases.
        walk_path = ASSETS / "player_walk.png"
        try:
            walk_atlas = pygame.image.load(str(walk_path)).convert_alpha()
        except (OSError, pygame.error) as exc:
            raise RuntimeError(f"Missing walking atlas: {walk_path}") from exc
        if walk_atlas.get_size() != (cell * 4, cell * 4):
            raise RuntimeError(
                f"Expected a {cell * 4}x{cell * 4} walking atlas, "
                f"got {walk_atlas.get_size()}")
        for row, direction in enumerate(("up", "down", "left", "right")):
            for frame in range(4):
                assets[f"walk_{direction}_{frame}"] = walk_atlas.subsurface(
                    pygame.Rect(frame * cell, row * cell, cell, cell)).copy()
        return assets

    @staticmethod
    @staticmethod
    def _make_background() -> pygame.Surface:
        """Dark atmosphere framing the existing board without touching tiles."""
        small = pygame.Surface((192, 128))
        for y in range(128):
            for x in range(192):
                dx, dy = (x - 96) / 128, (y - 52) / 114
                glow = max(0, 1 - dx * dx - dy * dy) ** 2
                small.set_at((x, y), (
                    round(6 + 8 * glow), round(21 + 16 * glow),
                    round(44 + 32 * glow)))
        backdrop = pygame.transform.smoothscale(small, (DESIGN_W, DESIGN_H))
        detail = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        # Quiet layered silhouettes only in the outside margins.
        shapes = (
            ([(0, 180), (64, 147), (124, 190), (154, 266), (84, 308), (0, 294)],
             (36, 72, 105, 42)),
            ([(0, 340), (74, 300), (133, 371), (192, 425), (122, 500), (0, 476)],
             (17, 47, 83, 76)),
            ([(0, 715), (88, 656), (176, 712), (158, 826), (82, 867), (0, 820)],
             (30, 67, 101, 48)),
            ([(1536, 188), (1474, 154), (1390, 210), (1364, 276),
              (1452, 310), (1536, 290)], (38, 75, 113, 39)),
            ([(1536, 395), (1466, 348), (1408, 418), (1360, 473),
              (1442, 520), (1536, 494)], (18, 48, 83, 72)),
            ([(1536, 721), (1478, 678), (1390, 744), (1376, 847),
              (1466, 866), (1536, 824)], (32, 72, 110, 45)),
        )
        for points, color in shapes:
            pygame.draw.polygon(detail, color, points)
        # Small warm lantern accent on the far left, away from play cells.
        for radius, alpha in ((113, 5), (83, 8), (55, 14)):
            pygame.draw.circle(detail, (255, 175, 73, alpha), (113, 330), radius)
        pygame.draw.line(detail, (80, 111, 144, 90),
                         (113, 222), (113, 297), 4)
        pygame.draw.rect(detail, (40, 60, 79, 190),
                         pygame.Rect(92, 298, 42, 59), border_radius=9)
        pygame.draw.rect(detail, (232, 161, 68, 150),
                         pygame.Rect(99, 308, 28, 38), border_radius=6)
        pygame.draw.line(detail, (42, 60, 73, 205), (112, 304), (112, 348), 3)
        # Nearly monochrome cargo silhouettes on the right.
        for cx, cy, width in ((1440, 752, 94), (1367, 824, 100)):
            crate = pygame.Rect(cx, cy, width, width)
            pygame.draw.rect(detail, (51, 88, 122, 58),
                             crate, border_radius=5)
            pygame.draw.rect(detail, (84, 127, 161, 58), crate,
                             3, border_radius=5)
            pygame.draw.line(detail, (92, 138, 172, 46),
                             crate.topleft, crate.bottomright, 3)
            pygame.draw.line(detail, (92, 138, 172, 46),
                             crate.topright, crate.bottomleft, 3)
        backdrop.blit(detail, (0, 0))
        return backdrop

    def _asset(self, name: str, size: int) -> pygame.Surface:
        key = name, size
        sprite = self.scale_cache.get(key)
        if sprite is None:
            # Character frames keep crisp edges; smoothscale softens tiny details.
            scaler = pygame.transform.scale if name.startswith("walk_") else pygame.transform.smoothscale
            sprite = scaler(self.assets[name], (size, size))
            self.scale_cache[key] = sprite
        return sprite

    def _player(self, size: int, walk_frame: int | None = None) -> pygame.Surface:
        """Idle uses phase zero; motion uses directional stepping frames."""
        frame = 0 if walk_frame is None else walk_frame
        return self._asset(f"walk_{self.facing}_{frame}", size)

    @staticmethod
    def _cell_origin(gx: float, gy: float, x0: int, y0: int,
                     tile: int) -> tuple[int, int]:
        """One grid origin shared by floors, walls, boxes, goals and the player."""
        return round(x0 + gx * tile), round(y0 + gy * tile)

    def _blit_cell(self, name: str, gx: float, gy: float,
                   x0: int, y0: int, tile: int,
                   walk_frame: int | None = None) -> None:
        sprite = (self._player(tile, walk_frame) if name == "player"
                  else self._asset(name, tile))
        self.canvas.blit(sprite, self._cell_origin(gx, gy, x0, y0, tile))

    def _draw_floor_cell(self, gx: int, gy: int, x0: int, y0: int,
                         tile: int) -> None:
        """Draw seams from the true logical grid, never from the floor PNG."""
        left, top = self._cell_origin(gx, gy, x0, y0, tile)
        cell = pygame.Rect(left, top, tile, tile)
        pygame.draw.rect(self.canvas, FLOOR_GROUT, cell)
        inset = cell.inflate(-4, -4)
        pygame.draw.rect(self.canvas, FLOOR_TILE, inset, border_radius=3)
        pygame.draw.line(self.canvas, FLOOR_HIGHLIGHT,
                         (inset.left + 4, inset.top + 1),
                         (inset.right - 5, inset.top + 1), 1)

    def _viewport(self) -> tuple[float, float, float]:
        w, h = self.screen.get_size()
        scale = min(w / DESIGN_W, h / DESIGN_H)
        return ((w - DESIGN_W * scale) / 2, (h - DESIGN_H * scale) / 2, scale)

    def _logical_point(self, pos: tuple[int, int]) -> tuple[float, float] | None:
        x, y, scale = self._viewport()
        px, py = (pos[0] - x) / scale, (pos[1] - y) / scale
        return (px, py) if 0 <= px < DESIGN_W and 0 <= py < DESIGN_H else None

    def _text(self, msg: str, font: str, position: tuple[int, int],
              color: tuple[int, int, int] = WHITE, center: bool = False) -> None:
        surface = self.fonts[font].render(msg, True, color)
        rect = surface.get_rect(center=position) if center else surface.get_rect(topleft=position)
        self.canvas.blit(surface, rect)

    def _panel(self, rect: pygame.Rect, bright: bool = False) -> None:
        """Calm common surface for modal dialogs."""
        pygame.draw.rect(self.canvas, (3, 11, 27),
                         rect.move(0, 7), border_radius=19)
        pygame.draw.rect(self.canvas, (18, 40, 68) if bright else (13, 32, 57),
                         rect, border_radius=19)
        pygame.draw.rect(self.canvas, (66, 107, 149),
                         rect, 2, border_radius=19)
        pygame.draw.line(self.canvas, (92, 140, 181),
                         (rect.left + 24, rect.top + 3),
                         (rect.right - 24, rect.top + 3), 1)

    def _button(self, rect: pygame.Rect, label: str, action: str,
                enabled: bool = True, variant: str = "blue",
                icon: str = "") -> None:
        """Unified interactive controls, distinct from unboxed information."""
        point = self._logical_point(pygame.mouse.get_pos())
        hover = enabled and point is not None and rect.collidepoint(point)
        palette = {
            "blue": ((29, 65, 105), (77, 126, 175)),
            "gold": ((122, 83, 29), (227, 168, 77)),
            "green": ((37, 111, 75), (108, 204, 135)),
            "gray": ((37, 62, 91), (92, 124, 155)),
        }
        surface, border = palette["gray" if not enabled else variant]
        if not enabled:
            surface, border = (33, 47, 67), (70, 87, 106)
        elif hover:
            surface = tuple(min(255, component + 13) for component in surface)
        pygame.draw.rect(self.canvas, (3, 12, 25),
                         rect.move(0, 4), border_radius=14)
        pygame.draw.rect(self.canvas, surface, rect, border_radius=14)
        pygame.draw.rect(self.canvas, border, rect, 2, border_radius=14)
        pygame.draw.line(self.canvas,
                         tuple(min(255, component + 18) for component in border),
                         (rect.x + 16, rect.y + 4),
                         (rect.right - 16, rect.y + 4), 1)

        foreground = WHITE if enabled else (151, 169, 187)
        if icon and not label:
            self._icon(icon, rect.center, foreground)
        else:
            shortcut = {"undo": "Z", "restart": "R", "next": "N"}.get(action)
            show_key = shortcut is not None and rect.width >= 300
            icon_slot = 46 if icon else 0
            key_slot = 35 if show_key else 0
            available = rect.width - icon_slot - key_slot - 36
            font_name = next(
                (name for name in ("medium", "small", "mini")
                 if self.fonts[name].size(label)[0] <= available),
                "mini",
            )
            if icon:
                self._icon(icon, (rect.x + 37, rect.centery), foreground)
            self._text(label, font_name,
                       (rect.centerx + (icon_slot - key_slot) // 2,
                        rect.centery - 1), foreground, center=True)
            if show_key:
                self._text(shortcut, "mini",
                           (rect.right - 27, rect.centery - 1),
                           (171, 198, 222) if enabled else (122, 144, 166),
                           center=True)
        self.buttons.append(Button(rect, action, enabled))

    def _icon(self, kind: str, center: tuple[int, int], c: tuple[int, int, int]) -> None:
        x, y = center
        if kind == "undo":
            pygame.draw.arc(self.canvas, c, pygame.Rect(x - 13, y - 10, 29, 27), math.radians(-75), math.radians(190), 5)
            pygame.draw.lines(self.canvas, c, False, [(x-7,y-17),(x-19,y-9),(x-7,y-1)],5)
        elif kind == "restart":
            pygame.draw.arc(self.canvas, c, pygame.Rect(x - 14, y - 14, 29, 29), .5, 5.4, 5)
            pygame.draw.polygon(self.canvas, c, [(x + 17, y - 10), (x + 19, y + 3), (x + 5, y - 2)])
        elif kind == "next":
            pygame.draw.lines(self.canvas, c, False, [(x-10,y-14),(x+5,y),(x-10,y+14)],5)
        elif kind == "menu":
            for j in (-10,0,10):
                pygame.draw.line(self.canvas, c,(x-13,y+j),(x+13,y+j),4)
        elif kind == "box":
            # Square icon viewed from above; never an isometric cube.
            pygame.draw.rect(self.canvas, c,(x-15,y-15,30,30),3,border_radius=3)
            pygame.draw.lines(self.canvas,c,False,[(x-11,y-11),(x+11,y+11)],3)
            pygame.draw.lines(self.canvas,c,False,[(x+11,y-11),(x-11,y+11)],3)
        elif kind == "footsteps":
            pygame.draw.ellipse(self.canvas,c,(x-14,y-12,10,17))
            pygame.draw.ellipse(self.canvas,c,(x+3,y+1,10,17))
            pygame.draw.circle(self.canvas,c,(x-4,y-14),4)
            pygame.draw.circle(self.canvas,c,(x+14,y-3),4)

    def _header(self) -> None:
        """Consistent HUD: labels are information, only the menu is clickable."""
        pygame.draw.rect(self.canvas, (8, 25, 47),
                         pygame.Rect(0, 0, DESIGN_W, 110))
        pygame.draw.line(self.canvas, (45, 84, 122),
                         (0, 108), (DESIGN_W, 108), 2)
        pygame.draw.line(self.canvas, (222, 164, 69),
                         (44, 108), (347, 108), 2)

        self.canvas.blit(self._asset("crate", 65), (38, 22))
        self._text("Sokoban", "brand", (118, 20))

        self._text("УРОВЕНЬ", "mini", (555, 24), MUTED)
        self._text(f"{self.game.level_index + 1} / {len(self.game.levels)}",
                   "big", (554, 49))

        self._icon("footsteps", (865, 58), (178, 204, 224))
        self._text("ХОДЫ", "mini", (907, 24), MUTED)
        self._text(str(self.game.moves), "big", (906, 50))

        self._icon("box", (1109, 58), (221, 169, 82))
        self._text("ЯЩИКИ НА ЦЕЛИ", "mini", (1152, 24), MUTED)
        self._text(f"{self.game.boxes_on_goals} / {len(self.game.boxes)}",
                   "big", (1150, 50))

        self._button(pygame.Rect(1413, 23, 72, 64), "",
                     "menu", icon="menu")

    def _board_geometry(self) -> tuple[int, int, int]:
        rows = self.game.level.rows
        cols, nr = len(rows[0]), len(rows)
        # All levels use exactly the same logical tile size. Only the
        # board's centered origin changes when a level has fewer cells.
        tile = GAME_TILE_SIZE
        x = (DESIGN_W - cols * tile) // 2
        y = 118 + (784 - nr * tile) // 2
        return x, y, tile

    @staticmethod
    def _outside_tiles(rows: tuple[str, ...]) -> set[tuple[int, int]]:
        """Mark exterior whitespace to keep irregular levels silhouetted."""
        height, width = len(rows), len(rows[0])
        frontier = deque()
        seen: set[tuple[int, int]] = set()
        for y in range(height):
            for x in (0, width - 1):
                if rows[y][x] == " ":
                    seen.add((x, y)); frontier.append((x, y))
        for x in range(width):
            for y in (0, height - 1):
                if rows[y][x] == " ":
                    seen.add((x, y)); frontier.append((x, y))
        while frontier:
            x, y = frontier.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = x + dx, y + dy
                if (0 <= n[0] < width and 0 <= n[1] < height
                        and n not in seen and rows[n[1]][n[0]] == " "):
                    seen.add(n)
                    frontier.append(n)
        return seen

    def _goal_glow_progress(self, now: int) -> float | None:
        glow = self.goal_glow
        if glow is None:
            return None
        if glow.position not in self.game.goals or glow.position not in self.game.boxes:
            self.goal_glow = None
            return None
        elapsed = now - glow.start
        if elapsed >= GOAL_GLOW_MS:
            self.goal_glow = None
            return None
        return elapsed / GOAL_GLOW_MS if elapsed >= 0 else None

    def _draw_goal_glow(self, pos: tuple[int, int], x0: int, y0: int,
                        tile: int, phase: float) -> None:
        """Temporary green outline over a crate; no bitmap resampling."""
        intensity = round(210 * math.sin(math.pi * phase))
        if intensity <= 0:
            return
        overlay = pygame.Surface((tile, tile), pygame.SRCALPHA)
        radius = max(8, round(tile * 0.13))
        pygame.draw.rect(
            overlay, (79, 227, 117, intensity // 7),
            pygame.Rect(6, 6, tile - 12, tile - 12), border_radius=radius)
        for inset, width, alpha in ((1, 2, intensity // 4),
                                    (4, 3, intensity),
                                    (8, 2, intensity // 3)):
            pygame.draw.rect(
                overlay, (100, 255, 148, alpha),
                pygame.Rect(inset, inset, tile - 2 * inset, tile - 2 * inset),
                width=width, border_radius=radius)
        self.canvas.blit(overlay, self._cell_origin(*pos, x0, y0, tile))

    def _board_layer(self) -> None:
        rows = self.game.level.rows
        x0, y0, tile = self._board_geometry()
        self._board = x0, y0, tile
        outside = self._outside_tiles(rows)
        walls = self.game.walls
        # Floor grout and tile centers follow the exact logical grid.
        # Wall cells receive no floor to prevent bright corner leaks.
        for gy, row in enumerate(rows):
            for gx, _ in enumerate(row):
                if (gx, gy) in outside or (gx, gy) in walls:
                    continue
                self._draw_floor_cell(gx, gy, x0, y0, tile)

        for gx, gy in sorted(walls, key=lambda pos: (pos[1], pos[0])):
            if (gx, gy) in outside:
                continue
            left, top = self._cell_origin(gx, gy, x0, y0, tile)
            # The previous opaque navy square behind each rounded sprite
            # caused sharp dark corners. Keep joins between adjoining walls
            # filled, but round only corners exposed on BOTH adjoining sides.
            up = (gx, gy - 1) in walls
            down = (gx, gy + 1) in walls
            west = (gx - 1, gy) in walls
            east = (gx + 1, gy) in walls
            radius = max(5, round(tile * 0.095))
            # Back the transparent rounded corners of isolated INNER walls
            # with floor grout, but not any corner touching the exterior.
            # The atlas wall has ~15% transparent margins. A patch sized to
            # the backplate radius alone (7 px) leaves visible navy wedges.
            corner_size = max(2, round(tile * 0.23))
            cols, height = len(rows[0]), len(rows)
            corner_specs = (
                ((-1, 0), (0, -1), (-1, -1), 0, 0),
                ((1, 0), (0, -1), (1, -1), tile - corner_size, 0),
                ((-1, 0), (0, 1), (-1, 1), 0, tile - corner_size),
                ((1, 0), (0, 1), (1, 1),
                 tile - corner_size, tile - corner_size),
            )
            for side_a, side_b, diagonal, ox, oy in corner_specs:
                neighbors = tuple((gx + dx, gy + dy)
                                  for dx, dy in (side_a, side_b, diagonal))
                if (all(0 <= nx < cols and 0 <= ny < height
                        and (nx, ny) not in outside for nx, ny in neighbors)
                        and all((gx + dx, gy + dy) not in walls
                                for dx, dy in (side_a, side_b))):
                    pygame.draw.rect(
                        self.canvas, FLOOR_GROUT,
                        pygame.Rect(left + ox, top + oy,
                                    corner_size, corner_size),
                    )
            pygame.draw.rect(
                self.canvas, (60, 99, 156),
                pygame.Rect(left, top, tile, tile),
                border_top_left_radius=radius if not up and not west else 0,
                border_top_right_radius=radius if not up and not east else 0,
                border_bottom_left_radius=radius if not down and not west else 0,
                border_bottom_right_radius=radius if not down and not east else 0,
            )
            self._blit_cell("wall", gx, gy, x0, y0, tile)

        for gx, gy in self.game.goals:
            self._blit_cell("goal", gx, gy, x0, y0, tile)
        anim = self.animation
        now = pygame.time.get_ticks()
        pct = 1.0
        if anim:
            pct = min(1.0, max(0.0, (now - anim.start) / MOVE_MS))
            if pct >= 1:
                self.animation = None
        eased = pct * pct * (3 - 2 * pct)
        for gx, gy in self.game.boxes:
            if anim and pct < 1 and (gx,gy) == anim.box_target:
                continue
            self._blit_cell("crate", gx, gy, x0, y0, tile)
        if anim and pct < 1 and anim.box_source and anim.box_target:
            bx = anim.box_source[0] + (anim.box_target[0] - anim.box_source[0]) * eased
            by = anim.box_source[1] + (anim.box_target[1] - anim.box_source[1]) * eased
            self._blit_cell("crate", bx, by, x0, y0, tile)
        # Keep the glow visible along the crate edge after movement completes.
        phase = self._goal_glow_progress(now)
        if phase is not None and self.goal_glow is not None:
            self._draw_goal_glow(self.goal_glow.position, x0, y0, tile, phase)
        px, py = self.game.player
        if anim and pct < 1:
            px = anim.source[0] + (anim.target[0] - anim.source[0]) * eased
            py = anim.source[1] + (anim.target[1] - anim.source[1]) * eased
        # Advance the walk phases using the same 180ms movement interpolation.
        # No sprite rotation or secondary origin shifts.
        walk_frame = min(3, int(pct * 4)) if anim and pct < 1.0 else None
        self._blit_cell("player", px, py, x0, y0, tile,
                        walk_frame=walk_frame)

    def _victory_ready(self) -> bool:
        """Show success only after the last box has finished animating."""
        return (self.game.is_won and self.animation is None
                and self.goal_glow is None)

    def _footer(self) -> None:
        """Unified bottom toolbar, away from the unchanged 78px board."""
        pygame.draw.rect(self.canvas, (7, 22, 43),
                         pygame.Rect(0, 911, DESIGN_W, DESIGN_H - 911))
        pygame.draw.line(self.canvas, (38, 76, 115),
                         (0, 911), (DESIGN_W, 911), 2)
        y = 935
        self._button(pygame.Rect(224, y, 350, 66), "Отменить", "undo",
                     variant="blue", icon="undo")
        self._button(pygame.Rect(593, y, 350, 66), "Заново", "restart",
                     variant="blue", icon="restart")
        can_advance = (self._victory_ready()
                       and self.game.level_index < len(self.game.levels) - 1)
        self._button(pygame.Rect(962, y, 350, 66), "Следующий уровень", "next",
                     enabled=can_advance, variant="green", icon="next")

    def _win_overlay(self, progress: float) -> None:
        """Fade in the victory modal without altering any game artwork."""
        shade = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        shade.fill((5, 16, 36, round(150 * progress)))
        self.canvas.blit(shade, (0, 0))

        # Draw modal contents onto a separate alpha canvas. The base board
        # remains untouched and the actual button hitboxes never move.
        original = self.canvas
        modal = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        self.canvas = modal
        try:
            panel = pygame.Rect(504, 294, 528, 416)
            self._panel(panel, bright=True)

            # A restrained success emblem, using vector primitives only.
            center = (768, 358)
            pygame.draw.circle(self.canvas, (26, 83, 66), center, 36)
            pygame.draw.circle(self.canvas, (78, 195, 111), center, 36, 3)
            pygame.draw.lines(
                self.canvas, (197, 255, 205), False,
                [(754, 358), (764, 369), (783, 346)], 6)

            self._text("УРОВЕНЬ ПРОЙДЕН!", "big",
                       (768, 425), (255, 211, 102), center=True)
            last_level = self.game.level_index == len(self.game.levels) - 1
            note = ("Все уровни завершены" if last_level else
                    f"Уровень {self.game.level_index + 1} из {len(self.game.levels)}")
            self._text(note, "small", (768, 471), MUTED, center=True)

            pygame.draw.line(self.canvas, (69, 116, 172),
                             (552, 496), (984, 496), 2)
            self._text(f"Ходов: {self.game.moves}", "medium",
                       (768, 528), center=True)
            self._text(
                f"Ящиков на местах: {self.game.boxes_on_goals} / {len(self.game.goals)}",
                "small", (768, 568), center=True)

            # Both actions are equal-sized and stay at fixed coordinates.
            primary_action = "menu" if last_level else "next"
            primary_label = "Меню уровней" if last_level else "Следующий уровень"
            self._button(pygame.Rect(527, 620, 237, 60),
                         primary_label, primary_action, variant="gold")
            self._button(pygame.Rect(773, 620, 237, 60),
                         "Заново", "restart", variant="gray")
        finally:
            self.canvas = original

        # A subtle 10 px rise accompanies opacity; click targets remain fixed.
        modal.set_alpha(round(255 * progress))
        self.canvas.blit(modal, (0, round(10 * (1 - progress))))

    def _menu_overlay(self) -> None:
        """Level selector in the same visual style as all other controls."""
        if not self.menu_open:
            return
        overlay = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        overlay.fill((4, 14, 30, 201))
        self.canvas.blit(overlay, (0, 0))
        self.buttons = []
        card = pygame.Rect(508, 247, 520, 525)
        self._panel(card, bright=True)
        self._text("Уровни", "big", (card.centerx, 300), center=True)
        self._text("Выберите уровень", "small",
                   (card.centerx, 341), MUTED, center=True)
        for idx, level in enumerate(self.game.levels):
            current = idx == self.game.level_index
            self._button(
                pygame.Rect(card.centerx - 181, 376 + idx * 78, 362, 62),
                f"Уровень {idx + 1}", f"level:{idx}",
                variant="gold" if current else "blue",
            )
        self._button(pygame.Rect(card.centerx - 140, 660, 280, 64),
                     "Продолжить", "close", variant="gray")

    def _draw(self) -> None:
        self.canvas.blit(self.background, (0,0))
        self.buttons.clear()
        self._header()
        self._board_layer()
        self._footer()
        if self._victory_ready():
            self.buttons.clear()  # Modal owns input; never click through.
            progress = self._victory_progress(pygame.time.get_ticks())
            self._win_overlay(progress)
            if progress < 1.0:
                # Invisible/fading controls must not be clickable.
                self.buttons.clear()
        else:
            self.victory_started_at = None
        if self.menu_open:
            self._menu_overlay()
        if self.toast and pygame.time.get_ticks() < self.toast_until and not self.menu_open:
            msg = self.fonts["small"].render(self.toast, True, WHITE)
            r = msg.get_rect(center=(768, 892)).inflate(32, 16)
            pygame.draw.rect(self.canvas, (27, 53, 89), r, border_radius=12)
            self.canvas.blit(msg, msg.get_rect(center=r.center))
        x, y, scale = self._viewport()
        self.screen.fill((4, 13, 26))
        w, h = round(DESIGN_W*scale), round(DESIGN_H*scale)
        scaled = pygame.transform.smoothscale(self.canvas,(w,h)) if (w,h) != (DESIGN_W,DESIGN_H) else self.canvas
        self.screen.blit(scaled, (round(x), round(y)))
        pygame.display.flip()

    def _show(self, msg: str) -> None:
        self.toast = msg
        self.toast_until = pygame.time.get_ticks() + 1150

    def _clear_direction_input(self) -> None:
        """Never carry a held key or buffered turn across UI actions."""
        self._held_directions.clear()
        self._queued_direction = None

    def _direction_pressed(self, key: int, direction: tuple[int, int]) -> None:
        """Accept a tap immediately, or buffer one turn during an animation."""
        if self.menu_open or self.game.is_won or key in self._held_directions:
            return
        self._held_directions[key] = direction
        if self.animation is not None:
            # A fast tap during the previous step must not be lost even if
            # the player releases the key before the animation completes.
            self._queued_direction = direction
        else:
            self._move(*direction)

    def _release_direction(self, key: int) -> None:
        """Releasing a key stops repeat, without discarding an already-tapped turn."""
        self._held_directions.pop(key, None)

    def _step_held(self) -> None:
        """Advance held controls by one logical tile after each animation."""
        if self.menu_open or self.game.is_won:
            return
        if self.animation is not None:
            if pygame.time.get_ticks() - self.animation.start < MOVE_MS:
                return
            # The renderer also finishes animations, but input should not
            # depend on the ordering of display frames or missed key repeats.
            self.animation = None
        direction = self._queued_direction
        self._queued_direction = None
        if direction is None and self._held_directions:
            direction = self._held_directions[next(reversed(self._held_directions))]
        if direction is not None:
            self._move(*direction)

    def _move(self, dx: int, dy: int) -> None:
        if self.animation or self.game.is_won or self.menu_open:
            return
        source = self.game.player
        boxes = set(self.game.boxes)
        if not self.game.move(dx,dy):
            return
        self.facing = {(0, -1): "up", (0, 1): "down",
                       (-1, 0): "left", (1, 0): "right"}[(dx, dy)]
        gone = boxes - self.game.boxes
        arrived = self.game.boxes - boxes
        source_box = next(iter(gone)) if gone else None
        target_box = next(iter(arrived)) if arrived else None
        now = pygame.time.get_ticks()
        self.animation = MoveAnimation(source, self.game.player, now,
                                       source_box, target_box)
        if self.goal_glow and self.goal_glow.position not in self.game.boxes:
            self.goal_glow = None
        if target_box is not None and target_box in self.game.goals:
            self.goal_glow = GoalGlow(target_box, now + MOVE_MS)

    def _undo(self) -> None:
        self.victory_started_at = None
        self._clear_direction_input()
        self.animation = None
        self.goal_glow = None
        if not self.game.undo():
            self._show("Нет ходов для отмены")

    def _restart(self) -> None:
        self.victory_started_at = None
        self._clear_direction_input()
        self.game.restart()
        self.animation = None
        self.goal_glow = None
        self.facing = "up"
        self.menu_open = False

    def _next(self) -> None:
        if (self._victory_ready()
                and self.victory_started_at is not None
                and pygame.time.get_ticks() - self.victory_started_at >= VICTORY_REVEAL_MS
                and self.game.next_level()):
            self.victory_started_at = None
            self._clear_direction_input()
            self.animation = None
            self.goal_glow = None
            self.facing = "up"
            self.menu_open = False

    def _click(self, pos: tuple[int,int]) -> None:
        p = self._logical_point(pos)
        if p is None:
            return
        for btn in reversed(self.buttons):
            if not btn.enabled or not btn.rect.collidepoint(p):
                continue
            action = btn.action
            if action == "undo": self._undo()
            elif action == "restart": self._restart()
            elif action == "next": self._next()
            elif action == "menu":
                self._clear_direction_input()
                self.menu_open = not self.menu_open
            elif action == "close":
                self._clear_direction_input()
                self.menu_open = False
            elif action.startswith("level:"):
                self._clear_direction_input()
                idx = int(action.partition(":")[2])
                self.game = Game(levels=self.game.levels,level_index=idx)
                self.victory_started_at = None
                self.animation = None
                self.goal_glow = None
                self.facing = "up"
                self.menu_open = False
            return

    def _key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self._clear_direction_input()
            if self.menu_open:
                self.menu_open = False
            else:
                self.running = False
            return
        if self.menu_open:
            return
        char = getattr(event, "unicode", "").lower()
        direction = DIRECTION_KEYS.get(event.key, DIRECTION_CHARS.get(char))
        if direction is not None:
            self._direction_pressed(event.key, direction)
        elif event.key == pygame.K_BACKSPACE or char in ("z", "я", "u", "г"):
            self._undo()
        elif event.key == pygame.K_r or char == "к":
            self._restart()
        elif event.key == pygame.K_n or char == "т":
            self._next()

    def run(self) -> None:
        try:
            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.VIDEORESIZE:
                        self.screen = pygame.display.set_mode((max(640, event.w), max(480, event.h)), pygame.RESIZABLE)
                    elif event.type == pygame.KEYDOWN:
                        self._key(event)
                    elif event.type == pygame.KEYUP:
                        self._release_direction(event.key)
                    elif event.type == pygame.WINDOWFOCUSLOST:
                        self._clear_direction_input()
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._click(event.pos)
                self._step_held()
                self._draw()
                self.clock.tick(FPS)
        finally:
            pygame.quit()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Top-down Sokoban")
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--screenshot", metavar="FILE", default=None,
                        help="capture a real frame in Pygame (SDL dummy driver supported)")
    args = parser.parse_args()
    if not 1 <= args.level <= len(LEVELS):
        parser.error(f"--level must be 1..{len(LEVELS)}")
    app = FlatSokobanApp(start_level=args.level - 1)
    if args.screenshot:
        try:
            app._draw()
            pygame.image.save(app.screen, args.screenshot)
        finally:
            pygame.quit()
    else:
        app.run()


if __name__ == "__main__":
    main()
