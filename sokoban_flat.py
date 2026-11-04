"""Fixed-layout, top-down Sokoban UI inspired by the approved 2D screen.

The game logic still lives entirely in ``sokoban.Game``. Presentation uses five consistent, transparent sprites prepared from the
approved design reference; no isometric or perspective renderer.
"""
from __future__ import annotations

import io
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
        logo = pygame.image.load(str(ASSETS / "sokoban_logo.png")).convert_alpha()
        logo = logo.subsurface(logo.get_bounding_rect(min_alpha=16)).copy()
        logo_scale = min(320 / logo.get_width(), 76 / logo.get_height())
        self.logo = pygame.transform.smoothscale(
            logo, (round(logo.get_width() * logo_scale), round(logo.get_height() * logo_scale)))
        plaque = pygame.image.load(str(ASSETS / "wooden_plaque.png")).convert_alpha()
        self.header_plaque = self._fit_plaque(plaque, (780, 112))
        self.footer_plaque = self._fit_plaque(plaque, (1150, 115))
        self.scale_cache: dict[tuple[str, int], pygame.Surface] = {}
        self.action_icon_cache: dict[tuple[str, tuple[int, int, int]], pygame.Surface] = {}
        self.facing = "up"  # sprite direction, never rotate a top-down character
        font_path = str(Path(__file__).resolve().parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf")
        self.fonts = {name: pygame.font.Font(font_path, size) for name, size in (
            ("brand", 46), ("big", 30), ("medium", 25),
            ("small", 20), ("mini", 18),
        )}
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

    @staticmethod
    def _fit_plaque(source: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        """Keep the carved ends and central ornament proportional as the panel widens."""
        width, height = size
        scaled_width = round(source.get_width() * height / source.get_height())
        artwork = pygame.transform.smoothscale(source, (scaled_width, height))
        if width <= scaled_width:
            return pygame.transform.smoothscale(source, size)
        left_cut, right_cut = scaled_width // 4, scaled_width * 3 // 4
        extra_left = (width - scaled_width) // 2
        extra_right = width - scaled_width - extra_left
        result = pygame.Surface(size, pygame.SRCALPHA)
        result.blit(artwork, (0, 0), (0, 0, left_cut, height))
        for cut, extra, x in ((left_cut, extra_left, left_cut),
                              (right_cut, extra_right, right_cut + extra_left)):
            strip = artwork.subsurface((cut, 0, 1, height))
            result.blit(pygame.transform.scale(strip, (extra, height)), (x, 0))
        result.blit(artwork, (left_cut + extra_left, 0),
                    (left_cut, 0, right_cut - left_cut, height))
        result.blit(artwork, (right_cut + extra_left + extra_right, 0),
                    (right_cut, 0, scaled_width - right_cut, height))
        return result

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
    def _make_background() -> pygame.Surface:
        """Build the navy backdrop and center the warehouse illustration behind the board."""
        small = pygame.Surface((192, 128))
        for y in range(128):
            for x in range(192):
                dx = (x - 96) / 120
                dy = (y - 51) / 105
                glow = max(0, 1 - (dx*dx + dy*dy)) ** 2
                small.set_at((x, y),
                             (round(7 + 6 * glow),
                              round(23 + 15 * glow),
                              round(48 + 28 * glow)))
        background = pygame.transform.smoothscale(small, (DESIGN_W, DESIGN_H))
        artwork = pygame.image.load(str(ASSETS / "warehouse_background.png")).convert()
        area = pygame.Rect(0, 118, DESIGN_W, 784)
        scale = max(area.width / artwork.get_width(), area.height / artwork.get_height())
        artwork = pygame.transform.smoothscale(
            artwork, (round(artwork.get_width() * scale), round(artwork.get_height() * scale)))
        background.set_clip(area)
        background.blit(artwork, artwork.get_rect(center=area.center))
        background.set_clip(None)
        return background

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
        pygame.draw.rect(self.canvas, (8, 10, 18), rect.move(0, 8), border_radius=20)
        pygame.draw.rect(self.canvas, (96, 57, 33), rect, border_radius=20)
        pygame.draw.rect(self.canvas, (188, 127, 64), rect, 2, border_radius=20)
        inner = rect.inflate(-14, -14)
        pygame.draw.rect(self.canvas, (27, 42, 48) if bright else (24, 39, 45), inner, border_radius=14)
        pygame.draw.rect(self.canvas, (112, 90, 61), inner, 1, border_radius=14)
        for x in (rect.x + 18, rect.right - 18):
            for y in (rect.y + 18, rect.bottom - 18):
                pygame.draw.circle(self.canvas, (227, 177, 100), (x, y), 3)

    def _button(self, rect: pygame.Rect, label: str, action: str, enabled: bool = True,
                variant: str = "blue", icon: str = "") -> None:
        mouse = self._logical_point(pygame.mouse.get_pos())
        hover = enabled and mouse is not None and rect.collidepoint(mouse)
        if icon and action in ("undo", "restart", "next"):
            # Low-profile toolbar actions with a separate keyboard keycap.
            button = rect.inflate(-8, -14)
            if hover:
                highlight = rect.inflate(-20, -36)
                pygame.draw.rect(self.canvas, (48, 63, 78), highlight, border_radius=8)
            ink = (244, 235, 219) if enabled else (126, 133, 139)
            icon_center = (button.x + 32, button.centery)
            pygame.draw.circle(self.canvas, (58, 75, 85) if enabled else (37, 48, 57), icon_center, 24)
            self._action_icon(icon, icon_center, (238, 198, 132) if enabled else (112, 120, 123))
            hint = {"undo": "Z", "restart": "R", "next": "N"}[action]
            label_surface = self.fonts["mini"].render(label, True, ink)
            self.canvas.blit(label_surface, label_surface.get_rect(midleft=(button.x + 65, button.centery)))
            key_rect = pygame.Rect(button.right - 42, button.centery - 15, 28, 30)
            pygame.draw.rect(self.canvas, (20, 30, 42), key_rect, border_radius=4)
            pygame.draw.rect(self.canvas, (90, 106, 112) if enabled else (57, 68, 72), key_rect, 1, border_radius=4)
            self._text(hint, "mini", key_rect.center, ink, center=True)
            self.buttons.append(Button(rect, action, enabled))
            return
        colors = {
            "blue": ((47, 75, 77), (67, 107, 106), (112, 145, 133)),
            "gold": ((151, 94, 43), (210, 150, 70), (235, 186, 111)),
            "green": ((27, 129, 66), (53, 167, 82), (128, 218, 139)),
            "gray": ((49, 66, 68), (68, 85, 83), (105, 129, 119)),
        }
        dark, base, border = colors[variant if enabled else "gray"]
        pygame.draw.rect(self.canvas, (3, 10, 23), rect.move(0, 5), border_radius=18)
        fill = tuple(min(255, x + (16 if hover else 0)) for x in dark)
        pygame.draw.rect(self.canvas, fill, rect, border_radius=18)
        pygame.draw.rect(self.canvas, border, rect, 2, border_radius=18)
        text_color = WHITE if enabled else (164, 185, 210)
        # The icon and caption have independent slots: captions never overlap icons
        # and must fit inside their buttons at every window size.
        icon_space = 72 if icon else 0
        usable = rect.width - icon_space - 30
        font_name = next((name for name in ("medium", "small", "mini")
                          if self.fonts[name].size(label)[0] <= usable), "mini")
        if icon:
            pygame.draw.circle(self.canvas, base, (rect.x + 38, rect.centery), 25)
            self._icon(icon, (rect.x + 38, rect.centery), text_color)
        center_x = rect.x + icon_space + (rect.width - icon_space) // 2
        self._text(label, font_name, (center_x, rect.centery - 2), text_color, center=True)
        self.buttons.append(Button(rect, action, enabled))

    def _action_icon(self, kind: str, center: tuple[int, int], color: tuple[int, int, int]) -> None:
        """Load Lucide SVG icons at high resolution and cache the tinted result."""
        key = (kind, color)
        sprite = self.action_icon_cache.get(key)
        if sprite is None:
            filename = {"undo": "undo-2", "restart": "rotate-ccw",
                        "next": "arrow-right-to-line"}[kind]
            path = Path(__file__).resolve().parent / "assets" / "icons" / "lucide" / f"{filename}.svg"
            svg = path.read_text(encoding="utf-8")
            svg = svg.replace("currentColor", "#{:02x}{:02x}{:02x}".format(*color))
            svg = svg.replace('width="24"', 'width="128"').replace('height="24"', 'height="128"')
            image = pygame.image.load(io.BytesIO(svg.encode("utf-8")), "icon.svg").convert_alpha()
            sprite = pygame.transform.smoothscale(image, (32, 32))
            self.action_icon_cache[key] = sprite
        self.canvas.blit(sprite, sprite.get_rect(center=center))

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
        """Separated title, status plaque and level selector."""
        self.canvas.blit(self.logo, self.logo.get_rect(midleft=(35, 52)))
        plaque = pygame.Rect(400, 17, 736, 70)
        self.canvas.blit(self.header_plaque, (378, -4))
        for x in (650, 865):
            pygame.draw.line(self.canvas, (80, 96, 96), (x, 31), (x, 73), 1)
        level_badge = pygame.Rect(413, 27, 50, 50)
        pygame.draw.rect(self.canvas, (164, 111, 53), level_badge, border_radius=10)
        self._text(str(self.game.level_index + 1), "medium", level_badge.center,
                   (255, 241, 211), center=True)
        self._text("LEVEL", "mini", (479, 27), (175, 184, 171))
        self._text(f"{self.game.level_index + 1} / {len(self.game.levels)}", "small", (479, 53), (255, 235, 198))
        for x, label, value in ((675, "MOVES", str(self.game.moves)),
                                 (890, "CRATES", f"{self.game.boxes_on_goals} / {len(self.game.boxes)}")):
            self._text(label, "mini", (x, 27), (175, 184, 171))
            self._text(value, "small", (x, 53), (255, 235, 198))
        menu = pygame.Rect(1260, 24, 225, 55)
        mouse = self._logical_point(pygame.mouse.get_pos())
        fill = (167, 113, 61) if mouse and menu.collidepoint(mouse) else (123, 79, 44)
        pygame.draw.rect(self.canvas, fill, menu, border_radius=9)
        pygame.draw.rect(self.canvas, (217, 163, 94), menu, 2, border_radius=9)
        self._text("CHOOSE LEVEL", "mini", menu.center, (255, 237, 207), center=True)
        self.buttons.append(Button(menu, "menu"))

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
        y = 927
        tray = pygame.Rect(214, 921, 1108, 88)
        self.canvas.blit(self.footer_plaque, (193, 907))
        for x in (584, 953):
            pygame.draw.line(self.canvas, (75, 91, 91), (x, 940), (x, 990), 1)
        # Three equal-width controls centered beneath the board.
        self._button(pygame.Rect(224, y, 350, 76), "Undo", "undo",
                     variant="blue", icon="undo")
        self._button(pygame.Rect(593, y, 350, 76), "Restart", "restart",
                     variant="blue", icon="restart")
        can_advance = self._victory_ready() and self.game.level_index < len(self.game.levels) - 1
        self._button(pygame.Rect(962, y, 350, 76), "Next level", "next",
                     enabled=can_advance, variant="gold", icon="next")

    def _victory_progress(self, now: int) -> float:
        """A single 280 ms reveal, starting only after the final box/glow."""
        if self.victory_started_at is None:
            self.victory_started_at = now
        elapsed = max(0, now - self.victory_started_at)
        linear = min(1.0, elapsed / VICTORY_REVEAL_MS)
        return linear * linear * (3 - 2 * linear)

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

            # Warm medal matches the brass and lanterns in the warehouse.
            center = (768, 358)
            pygame.draw.circle(self.canvas, (116, 71, 39), center, 38)
            pygame.draw.circle(self.canvas, (230, 174, 91), center, 36, 3)
            pygame.draw.circle(self.canvas, (165, 110, 52), center, 30)
            pygame.draw.lines(
                self.canvas, (255, 236, 190), False,
                [(754, 358), (764, 369), (783, 346)], 6)
            for x in (704, 832):
                pygame.draw.circle(self.canvas, (232, 185, 112), (x, 358), 3)

            self._text("LEVEL COMPLETE!", "big",
                       (768, 425), (255, 211, 102), center=True)
            last_level = self.game.level_index == len(self.game.levels) - 1
            note = ("All levels complete" if last_level else
                    f"Level {self.game.level_index + 1} of {len(self.game.levels)}")
            self._text(note, "small", (768, 471), MUTED, center=True)

            pygame.draw.line(self.canvas, (139, 112, 74),
                             (552, 496), (984, 496), 2)
            self._text(f"Moves: {self.game.moves}", "medium",
                       (768, 528), center=True)
            self._text(
                f"Crates on goals: {self.game.boxes_on_goals} / {len(self.game.goals)}",
                "small", (768, 568), center=True)

            # Both actions are equal-sized and stay at fixed coordinates.
            primary_action = "menu" if last_level else "next"
            primary_label = "Level select" if last_level else "Next level"
            self._button(pygame.Rect(527, 620, 237, 60),
                         primary_label, primary_action, variant="gold")
            self._button(pygame.Rect(773, 620, 237, 60),
                         "Restart", "restart", variant="gray")
        finally:
            self.canvas = original

        # A subtle 10 px rise accompanies opacity; click targets remain fixed.
        modal.set_alpha(round(255 * progress))
        self.canvas.blit(modal, (0, round(10 * (1 - progress))))

    def _menu_overlay(self) -> None:
        if not self.menu_open:
            return
        overlay = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        overlay.fill((2, 12, 31, 190))
        self.canvas.blit(overlay,(0,0))
        self.buttons = []  # Modal: only the menu receives clicks.
        card = pygame.Rect(508, 253, 520, 514)
        self._panel(card, bright=True)
        self._text("CHOOSE A LEVEL", "big", (card.centerx, 306), (255, 235, 198), center=True)
        self._text("Choose your next puzzle", "mini", (card.centerx, 341), (164, 181, 178), center=True)
        mouse = self._logical_point(pygame.mouse.get_pos())
        for idx, level in enumerate(self.game.levels):
            rect = pygame.Rect(card.centerx - 181, 367 + idx * 81, 362, 64)
            selected = idx == self.game.level_index
            hovered = mouse is not None and rect.collidepoint(mouse)
            fill = (87, 78, 56) if selected else (55, 75, 77) if hovered else (38, 58, 62)
            pygame.draw.rect(self.canvas, fill, rect, border_radius=10)
            pygame.draw.rect(self.canvas, (188, 147, 87) if selected else (83, 109, 106), rect, 2, border_radius=10)
            badge = pygame.Rect(rect.x + 10, rect.y + 10, 44, 44)
            pygame.draw.rect(self.canvas, (151, 104, 53) if selected else (63, 87, 87), badge, border_radius=8)
            self._text(str(idx + 1), "small", badge.center, (255, 239, 210), center=True)
            self._text(f"Level {idx + 1}", "small", (rect.x + 70, rect.y + 19), (255, 239, 210))
            if selected:
                pygame.draw.circle(self.canvas, (226, 180, 108), (rect.right - 24, rect.centery), 6)
            self.buttons.append(Button(rect, f"level:{idx}"))
        close = pygame.Rect(card.centerx - 140, 653, 280, 64)
        pygame.draw.rect(self.canvas, (50, 68, 71), close, border_radius=10)
        pygame.draw.rect(self.canvas, (100, 123, 119), close, 1, border_radius=10)
        self._text("Continue", "small", close.center, (233, 232, 213), center=True)
        self.buttons.append(Button(close, "close"))

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
            self._show("Nothing to undo")

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
