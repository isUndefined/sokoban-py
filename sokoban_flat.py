"""Fixed-layout, top-down Sokoban UI inspired by the approved 2D screen.

The game logic still lives entirely in ``sokoban.Game``. Presentation uses
five original transparent PNG assets; no isometric or perspective renderer.
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
MOVE_MS = 155
ASSETS = Path(__file__).resolve().parent / "assets" / "flat"
BG_TOP = (12, 29, 54)
BG_BOTTOM = (8, 24, 48)
WHITE = (244, 248, 255)
MUTED = (169, 187, 217)
ACCENT = (255, 188, 45)
BLUE = (60, 100, 156)
GREEN = (68, 194, 98)


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


class FlatSokobanApp:
    """A fixed virtual-canvas GUI that scales without rearranging the UI."""

    def __init__(self, start_level: int = 0) -> None:
        pygame.init()
        pygame.display.set_caption("Sokoban — Classic Puzzle")
        self.screen = pygame.display.set_mode((1280, 854), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.canvas = pygame.Surface((DESIGN_W, DESIGN_H)).convert()
        self.background = self._make_background()
        self.assets = self._load_assets()
        self.scale_cache: dict[tuple[str, int], pygame.Surface] = {}
        self.rotated_player_cache: dict[int, pygame.Surface] = {}
        self.fonts = {
            "brand": pygame.font.SysFont("dejavusans", 51, bold=True),
            "big": pygame.font.SysFont("dejavusans", 34, bold=True),
            "medium": pygame.font.SysFont("dejavusans", 27, bold=True),
            "small": pygame.font.SysFont("dejavusans", 22, bold=True),
            "mini": pygame.font.SysFont("dejavusans", 19),
        }
        self.game = Game(level_index=start_level)
        self.running = True
        self.buttons: list[Button] = []
        self.menu_open = False
        self.animation: MoveAnimation | None = None
        self.facing = 0  # 0/up, 90/left, 180/down, 270/right
        self._layout = (0.0, 0.0, 1.0)
        self._board = (0, 0, 0)
        self.toast = ""
        self.toast_until = 0
        pygame.key.set_repeat(185, 165)

    def _load_assets(self) -> dict[str, pygame.Surface]:
        names = ("floor", "wall", "crate", "goal", "player_up")
        assets = {}
        for name in names:
            path = ASSETS / f"{name}.png"
            try:
                assets[name] = pygame.image.load(str(path)).convert_alpha()
            except (OSError, pygame.error) as exc:
                raise RuntimeError(f"Missing 2D game asset: {path}") from exc
        return assets

    @staticmethod
    def _make_background() -> pygame.Surface:
        backdrop = pygame.Surface((DESIGN_W, DESIGN_H))
        for y in range(DESIGN_H):
            t = y / DESIGN_H
            c = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
            pygame.draw.line(backdrop, c, (0, y), (DESIGN_W, y))
        # Flat broad color accents, without a pseudo-3D environment.
        shade = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        pygame.draw.circle(shade, (32, 80, 142, 28), (DESIGN_W // 2, 430), 550)
        pygame.draw.circle(shade, (31, 66, 117, 16), (110, 880), 300)
        backdrop.blit(shade, (0, 0))
        return backdrop

    def _asset(self, name: str, size: int) -> pygame.Surface:
        key = name, size
        sprite = self.scale_cache.get(key)
        if sprite is None:
            sprite = pygame.transform.smoothscale(self.assets[name], (size, size))
            self.scale_cache[key] = sprite
        return sprite

    def _player(self, size: int) -> pygame.Surface:
        source = self.rotated_player_cache.get(self.facing)
        if source is None:
            source = pygame.transform.rotate(self.assets["player_up"], self.facing)
            self.rotated_player_cache[self.facing] = source
        return pygame.transform.smoothscale(source, (size, size))

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
        pygame.draw.rect(self.canvas, (3, 11, 27), rect.move(0, 5), border_radius=18)
        pygame.draw.rect(self.canvas, (21, 47, 80) if bright else (17, 37, 67), rect, border_radius=18)
        pygame.draw.rect(self.canvas, (69, 116, 172), rect, 3, border_radius=18)
        pygame.draw.line(self.canvas, (91, 139, 192), (rect.x + 16, rect.y + 4),
                         (rect.right - 16, rect.y + 4), 2)

    def _button(self, rect: pygame.Rect, label: str, action: str, enabled: bool = True,
                variant: str = "blue", icon: str = "") -> None:
        mouse = self._logical_point(pygame.mouse.get_pos())
        hover = enabled and mouse is not None and rect.collidepoint(mouse)
        colors = {
            "blue": ((41, 79, 127), (67, 107, 160), (111, 156, 208)),
            "gold": ((191, 118, 18), (251, 166, 35), (255, 208, 80)),
            "green": ((27, 129, 66), (53, 167, 82), (128, 218, 139)),
            "gray": ((55, 72, 98), (68, 85, 114), (111, 127, 156)),
        }
        dark, base, border = colors[variant if enabled else "gray"]
        pygame.draw.rect(self.canvas, (3, 10, 23), rect.move(0, 6), border_radius=17)
        pygame.draw.rect(self.canvas, dark, rect, border_radius=17)
        inner = rect.inflate(-6, -8)
        inner.y -= 2
        pygame.draw.rect(self.canvas, tuple(min(255, x + (14 if hover else 0)) for x in base), inner, border_radius=14)
        pygame.draw.rect(self.canvas, border, rect, 3, border_radius=17)
        pygame.draw.line(self.canvas, tuple(min(255, x + 25) for x in border),
                         (rect.x + 18, rect.y + 7), (rect.right - 18, rect.y + 7), 2)
        text_color = WHITE if enabled else (171, 188, 211)
        if icon:
            self._icon(icon, (rect.x + 42, rect.centery), text_color)
        self._text(label, "medium", (rect.centerx + (16 if icon else 0), rect.centery - 2),
                   text_color, center=True)
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
        pygame.draw.line(self.canvas, (48, 82, 132), (36, 105), (1498, 105), 2)
        self.canvas.blit(self._asset("crate", 68), (43, 11))
        self._text("Sokoban", "brand", (127, 9))
        pygame.draw.line(self.canvas, (57, 96, 153), (413, 17), (413, 78), 4)
        self._panel(pygame.Rect(473, 12, 345, 68), bright=True)
        self._text(f"Уровень {self.game.level_index + 1} / {len(self.game.levels)}", "big", (646, 45), center=True)
        self._icon("footsteps", (948, 45), WHITE)
        self._text("Ходы", "small", (973, 10))
        self._text(str(self.game.moves), "big", (995, 38))
        pygame.draw.line(self.canvas, (60, 100, 157), (1080, 18), (1080, 76), 4)
        self._icon("box", (1132, 45), WHITE)
        self._text("Ящики", "small", (1162, 10))
        self._text(f"{self.game.boxes_on_goals} / {len(self.game.boxes)}", "big", (1192, 38))
        self._panel(pygame.Rect(1404, 12, 75, 68))
        self._icon("menu", (1441, 46), WHITE)
        self.buttons.append(Button(pygame.Rect(1404, 12, 75, 68), "menu"))

    def _board_geometry(self) -> tuple[int, int, int]:
        rows = self.game.level.rows
        cols, nr = len(rows[0]), len(rows)
        tile = min(107, (990 - 40) // cols, (790 - 30) // nr)
        x = 200 + (1000 - cols * tile) // 2
        y = 118 + (788 - nr * tile) // 2
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

    def _board_layer(self) -> None:
        rows = self.game.level.rows
        x0, y0, tile = self._board_geometry()
        self._board = x0, y0, tile
        outside = self._outside_tiles(rows)
        # Cell-aligned flat silhouette, including non-rectangular level outlines.
        for gy, row in enumerate(rows):
            for gx, _ in enumerate(row):
                if (gx, gy) in outside:
                    continue
                shadow = pygame.Rect(x0 + gx * tile - 5, y0 + gy * tile + 6,
                                     tile + 10, tile + 10)
                pygame.draw.rect(self.canvas, (4, 14, 30), shadow, border_radius=10)
        for gy, row in enumerate(rows):
            for gx, _ in enumerate(row):
                if (gx, gy) in outside:
                    continue
                name = "wall" if (gx, gy) in self.game.walls else "floor"
                self.canvas.blit(self._asset(name, tile), (x0 + gx * tile, y0 + gy * tile))
        for gx, gy in self.game.goals:
            self.canvas.blit(self._asset("goal", tile), (x0 + gx * tile, y0 + gy * tile))
        anim = self.animation
        pct = 1.0
        if anim:
            pct = min(1.0, (pygame.time.get_ticks() - anim.start) / MOVE_MS)
            if pct >= 1:
                self.animation = None
        eased = pct * pct * (3 - 2 * pct)
        for gx, gy in self.game.boxes:
            if anim and pct < 1 and (gx,gy) == anim.box_target:
                continue
            self.canvas.blit(self._asset("crate", tile), (x0 + gx * tile, y0 + gy * tile))
        if anim and pct < 1 and anim.box_source and anim.box_target:
            bx = anim.box_source[0] + (anim.box_target[0] - anim.box_source[0]) * eased
            by = anim.box_source[1] + (anim.box_target[1] - anim.box_source[1]) * eased
            self.canvas.blit(self._asset("crate", tile), (round(x0 + bx * tile), round(y0 + by * tile)))
        px, py = self.game.player
        if anim and pct < 1:
            px = anim.source[0] + (anim.target[0] - anim.source[0]) * eased
            py = anim.source[1] + (anim.target[1] - anim.source[1]) * eased
        person_size = round(tile * 0.95)
        person = self._player(person_size)
        self.canvas.blit(person, (round(x0 + (px + .5) * tile - person_size / 2),
                                  round(y0 + (py + .5) * tile - person_size / 2)))

    def _footer(self) -> None:
        y = 927
        self._button(pygame.Rect(273, y, 296, 76), "Отменить", "undo", variant="blue", icon="undo")
        self._button(pygame.Rect(603, y, 296, 76), "Заново", "restart", variant="blue", icon="restart")
        can_advance = self.game.is_won and self.game.level_index < len(self.game.levels) - 1
        self._button(pygame.Rect(933, y, 330, 76), "Следующий уровень", "next",
                     enabled=can_advance, variant="gold", icon="next")

    def _win_overlay(self) -> None:
        if not self.game.is_won:
            return
        fade = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        fade.fill((5, 16, 36, 132))
        self.canvas.blit(fade, (0,0))
        panel = pygame.Rect(504, 323, 528, 336)
        self._panel(panel, bright=True)
        self._text("УРОВЕНЬ ПРОЙДЕН!", "big", (768, 402), (255, 203, 91), center=True)
        self._text(f"Ходов: {self.game.moves}  ·  Ящиков: {len(self.game.boxes)}", "medium", (768, 470), center=True)
        if self.game.level_index == len(self.game.levels) - 1:
            self._text("Все уровни завершены", "small", (768, 545), center=True)
            self._button(pygame.Rect(608, 566, 320, 60), "Меню уровней", "menu", variant="blue")
        else:
            self._button(pygame.Rect(589, 545, 358, 66), "Следующий уровень", "next", variant="gold")
        self._button(pygame.Rect(688, 607, 160, 45), "Заново", "restart", variant="gray")

    def _menu_overlay(self) -> None:
        if not self.menu_open:
            return
        overlay = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        overlay.fill((2, 12, 31, 190))
        self.canvas.blit(overlay,(0,0))
        self.buttons = []  # Modal: only the menu receives clicks.
        card = pygame.Rect(505, 260, 526, 500)
        self._panel(card, bright=True)
        self._text("ВЫБОР УРОВНЯ", "big", (768, 326), center=True)
        for idx, level in enumerate(self.game.levels):
            self._button(pygame.Rect(579, 366 + idx * 83, 378, 62),
                         f"{idx + 1}. {level.name}", f"level:{idx}", variant="blue")
        self._button(pygame.Rect(632, 642, 272, 65), "Продолжить", "close", variant="gray")

    def _draw(self) -> None:
        self.canvas.blit(self.background, (0,0))
        self.buttons.clear()
        self._header()
        self._board_layer()
        self._footer()
        if self.game.is_won:
            self.buttons.clear()  # Victory modal owns input until dismissed.
            self._win_overlay()
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

    def _move(self, dx: int, dy: int) -> None:
        if self.animation or self.game.is_won or self.menu_open:
            return
        source = self.game.player
        boxes = set(self.game.boxes)
        if not self.game.move(dx,dy):
            return
        self.facing = {(0,-1):0,(-1,0):90,(0,1):180,(1,0):270}[(dx,dy)]
        gone = boxes - self.game.boxes
        arrived = self.game.boxes - boxes
        self.animation = MoveAnimation(source,self.game.player,pygame.time.get_ticks(),
                                       next(iter(gone)) if gone else None,
                                       next(iter(arrived)) if arrived else None)

    def _undo(self) -> None:
        self.animation = None
        if not self.game.undo():
            self._show("Нет ходов для отмены")

    def _restart(self) -> None:
        self.game.restart()
        self.animation = None
        self.facing = 0
        self.menu_open = False

    def _next(self) -> None:
        if self.game.is_won and self.game.next_level():
            self.animation = None
            self.facing = 0
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
            elif action == "menu": self.menu_open = not self.menu_open
            elif action == "close": self.menu_open = False
            elif action.startswith("level:"):
                idx = int(action.partition(":")[2])
                self.game = Game(levels=self.game.levels,level_index=idx)
                self.animation = None
                self.facing = 0
                self.menu_open = False
            return

    def _key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            if self.menu_open: self.menu_open = False
            else: self.running = False
            return
        if self.menu_open:
            return
        char = event.unicode.lower()
        if event.key == pygame.K_UP or char in ("w", "ц"): self._move(0,-1)
        elif event.key == pygame.K_DOWN or char in ("s", "ы"): self._move(0,1)
        elif event.key == pygame.K_LEFT or char in ("a", "ф"): self._move(-1,0)
        elif event.key == pygame.K_RIGHT or char in ("d", "в"): self._move(1,0)
        elif event.key == pygame.K_BACKSPACE or char in ("z", "я", "u", "г"): self._undo()
        elif event.key == pygame.K_r or char == "к": self._restart()
        elif event.key == pygame.K_n or char == "т": self._next()

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
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._click(event.pos)
                self._draw()
                self.clock.tick(FPS)
        finally:
            pygame.quit()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Top-down Sokoban")
    parser.add_argument("--level", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.level <= len(LEVELS):
        parser.error(f"--level must be 1..{len(LEVELS)}")
    FlatSokobanApp(start_level=args.level - 1).run()


if __name__ == "__main__":
    main()