"""Locked art direction v1: warm, storybook-style isometric Sokoban.

This module owns presentation only. The Game class remains the single source
of truth for movement, goals, history, and puzzle completion.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pygame

from sokoban_gui import Button, SokobanApp

# Versioned design tokens. Gameplay/level changes must not change this layout.
DESIGN_SIZE = (1440, 960)
INK = (16, 19, 45)
PANEL = (29, 29, 66)
PANEL_LIGHT = (51, 49, 99)
PERIWINKLE = (184, 194, 247)
GOLD = (255, 202, 88)
GREEN = (107, 232, 52)
WHITE = (244, 244, 255)


class StorybookSokobanApp(SokobanApp):
    """Visual theme; original rules, save/undo, and animation are reused."""

    def __init__(self, start_level: int = 0) -> None:
        super().__init__(start_level)
        self.canvas = pygame.Surface(DESIGN_SIZE).convert()
        self.background = self._make_background()
        self._viewport = (0, 0, DESIGN_SIZE[0], DESIGN_SIZE[1])
        self._hero_cache: dict[tuple[int, int, int], pygame.Surface] = {}
        self._popup_buttons: list[Button] = []
        self.show_win_popup = True
        self.progress_path = Path.home() / ".sokoban-py-progress.json"
        self.best_moves: dict[str, int] = {}
        self.completed: set[int] = set()
        self._load_progress()
        self.title_font = pygame.font.SysFont("dejavusans", 48, bold=True)
        self.heading_font = pygame.font.SysFont("dejavusans", 25, bold=True)
        self.body_font = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.small_font = pygame.font.SysFont("dejavusans", 15)
        self.number_font = pygame.font.SysFont("dejavusans", 38, bold=True)

    def _load_progress(self) -> None:
        try:
            data = json.loads(self.progress_path.read_text(encoding="utf-8"))
            self.best_moves = {str(k): int(v) for k, v in data.get("best_moves", {}).items() if int(v) > 0}
            self.completed = {int(v) for v in data.get("completed", []) if 0 <= int(v) < len(self.game.levels)}
        except (OSError, ValueError, TypeError, AttributeError):
            self.best_moves, self.completed = {}, set()

    def _save_progress(self) -> None:
        try:
            data = {"version": 1, "best_moves": self.best_moves, "completed": sorted(self.completed)}
            self.progress_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass  # The game stays playable on read-only home directories.

    def _move(self, dx: int, dy: int) -> None:
        if self.animation and pygame.time.get_ticks() - self.animation.started_at < self.animation.duration:
            return  # Do not teleport the sprite by overwriting a running animation.
        was_won = self.game.is_won
        super()._move(dx, dy)
        if not was_won and self.game.is_won:
            index = self.game.level_index
            key = str(index)
            self.completed.add(index)
            self.best_moves[key] = min(self.game.moves, self.best_moves.get(key, self.game.moves))
            self.show_win_popup = True
            self._save_progress()

    def _undo(self) -> None:
        self.show_win_popup = False
        super()._undo()

    def _restart(self) -> None:
        self.show_win_popup = True
        super()._restart()

    def _select_level(self, index: int) -> None:
        if 0 <= index < len(self.game.levels):
            self.show_win_popup = True
            self._hero_cache.clear()
            super()._select_level(index)

    def _next_level(self) -> None:
        before = self.game.level_index
        super()._next_level()
        if self.game.level_index != before:
            self.show_win_popup = True
            self._popup_buttons.clear()

    def _handle_key(self, event: pygame.event.Event) -> None:
        if self.game.is_won and self.show_win_popup:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._next_level()
            elif event.key == pygame.K_ESCAPE:
                self.show_win_popup = False
            elif event.key == pygame.K_r:
                self._restart()
            return
        super()._handle_key(event)

    def _ui_mouse(self) -> tuple[int, int]:
        x, y, w, h = self._viewport
        mx, my = pygame.mouse.get_pos()
        return (int((mx - x) * DESIGN_SIZE[0] / max(1, w)),
                int((my - y) * DESIGN_SIZE[1] / max(1, h)))

    def _handle_click(self, pos: tuple[int, int]) -> None:
        vx, vy, vw, vh = self._viewport
        if not pygame.Rect(vx, vy, vw, vh).collidepoint(pos):
            return
        virtual = (int((pos[0] - vx) * DESIGN_SIZE[0] / vw),
                   int((pos[1] - vy) * DESIGN_SIZE[1] / vh))
        if self.game.is_won and self.show_win_popup:
            for button in self._popup_buttons:
                if button.enabled and button.rect.collidepoint(virtual):
                    if button.action == "next":
                        self._next_level()
                    elif button.action == "restart":
                        self._restart()
                    elif button.action == "menu":
                        self.show_win_popup = False
                    return
            return  # A modal must prevent clicks on the underlying HUD.
        for button in self.buttons:
            if button.enabled and button.rect.collidepoint(virtual):
                if button.action == "undo":
                    self._undo()
                elif button.action == "restart":
                    self._restart()
                elif button.action == "next":
                    self._next_level()
                elif button.action == "previous_level":
                    self._select_level(self.game.level_index - 1)
                elif button.action == "following_level":
                    self._select_level(self.game.level_index + 1)
                elif button.action == "settings":
                    self._show_toast("Arrows / WASD · Z undo · R retry")
                return

    def _draw(self) -> None:
        window = self.screen
        self.screen = self.canvas
        self.screen.blit(self.background, (0, 0))
        self.buttons = []
        self._draw_header(DESIGN_SIZE[0])
        self._draw_isometric_board(pygame.Rect(76, 135, 1000, 690))
        self._update_particles()
        self._draw_sidebar(pygame.Rect(1105, 128, 307, 732))
        self._draw_tip()
        if self.game.is_won and self.show_win_popup:
            self._draw_win_overlay(pygame.Rect(95, 160, 935, 650))
        self._draw_toast(*DESIGN_SIZE)
        self.screen = window
        w, h = window.get_size()
        factor = min(w / DESIGN_SIZE[0], h / DESIGN_SIZE[1])
        target = (max(1, round(DESIGN_SIZE[0] * factor)), max(1, round(DESIGN_SIZE[1] * factor)))
        offset = ((w - target[0]) // 2, (h - target[1]) // 2)
        self._viewport = (*offset, *target)
        window.fill((7, 10, 26))
        scaled = pygame.transform.smoothscale(self.canvas, target)
        window.blit(scaled, offset)

    def _make_background(self) -> pygame.Surface:
        w, h = DESIGN_SIZE
        surface = pygame.Surface(DESIGN_SIZE).convert()
        for y in range(h):
            t = y / h
            color = (round(16 + 21*t), round(17 + 13*t), round(37 + 18*t))
            pygame.draw.line(surface, color, (0, y), (w, y))
        rng = random.Random(1204)
        # Murky warehouse shadows, soft stone flecks and vegetation at the edges.
        for _ in range(480):
            x, y = rng.randrange(w), rng.randrange(h)
            c = (34, 36, 69) if rng.random() < .55 else (49, 40, 70)
            pygame.draw.circle(surface, c, (x, y), rng.randint(1, 3))
        for cx, cy, radius in [(-15, 35, 115), (1150, 30, 138), (1400, 820, 180), (48, 820, 120)]:
            for _ in range(46):
                x = cx + rng.randint(-radius, radius)
                y = cy + rng.randint(-radius, radius)
                r = rng.randint(19, 44)
                pygame.draw.ellipse(surface, rng.choice([(20, 46, 40), (22, 58, 39), (29, 70, 49), (16, 38, 39)]), (x-r,y-r,r*2,r*2))
        for x, y in ((27, 186), (1403, 284)):
            pygame.draw.line(surface, (79, 58, 69), (x, 0), (x, y), 8)
            pygame.draw.circle(surface, (241, 170, 66), (x, y), 33)
            pygame.draw.circle(surface, (255, 221, 110), (x, y), 20)
            pygame.draw.rect(surface, (107, 75, 66), pygame.Rect(x-25,y-33,50,65), 5, border_radius=8)
        # Crates and barrels outside the playable field lend it a diorama feel.
        for cx, cy, s in ((60, 570, 68), (145, 912, 73), (1010, 918, 72)):
            pygame.draw.rect(surface, (101, 55, 40), (cx,cy,s,s), border_radius=7)
            pygame.draw.rect(surface, (192, 114, 58), (cx+6,cy+6,s-12,s-12), 5)
            pygame.draw.line(surface, (230, 156, 80), (cx+10,cy+10), (cx+s-10,cy+s-10), 6)
            pygame.draw.line(surface, (209, 130, 69), (cx+s-10,cy+10), (cx+10,cy+s-10), 6)
        return surface

    def _draw_header(self, width: int) -> None:
        # Wooden-box logo, compact premium title, stable on every level.
        pygame.draw.rect(self.screen, (92, 45, 27), (40, 39, 70, 68), border_radius=8)
        pygame.draw.rect(self.screen, (230, 144, 67), (46, 44, 58, 55), 6, border_radius=5)
        pygame.draw.line(self.screen, GOLD, (50, 48), (100, 94), 7)
        pygame.draw.line(self.screen, (180, 102, 44), (98, 49), (52, 92), 6)
        self._shadow_text("SOKOBAN", self.title_font, (255, 191, 95), (127, 29))
        self._text("Push · Plan · Solve", self.small_font, (198, 202, 241), (197, 98))
        rect = pygame.Rect(width-105, 33, 64, 63)
        self._button(rect, "⚙", "settings", enabled=True, size=30)

    def _glow(self, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> None:
        # Normal alpha compositing avoids the opaque rectangular additive glow.
        layer = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
        for size, opacity in ((1, alpha//9), (.73, alpha//6), (.47, alpha//4), (.22, alpha//3)):
            r = round(radius*size)
            pygame.draw.circle(layer, (*color, opacity), (radius, radius), r)
        self.screen.blit(layer, (center[0]-radius, center[1]-radius))

    def _draw_isometric_board(self, area: pygame.Rect) -> None:
        rows = self.game.level.rows
        cols, row_count = len(rows[0]), len(rows)
        tile_w = max(32, min(112, int((area.width-95)*2/(cols+row_count)), int((area.height-110)*4/(cols+row_count))))
        tile_h = round(tile_w*.53)
        wall_h = round(tile_h*.9)
        ox = area.centerx - (cols-row_count)*tile_w/4
        oy = area.centery - (cols+row_count-2)*tile_h/4 + 24

        def project(pos: tuple[float, float]) -> tuple[int, int]:
            x, y = pos
            return (round(ox+(x-y)*tile_w/2), round(oy+(x+y)*tile_h/2))

        floor_centre = project(((cols-1)/2, (row_count-1)/2))
        pygame.draw.ellipse(self.screen, (12, 12, 31),
            (floor_centre[0]-area.width*.42, floor_centre[1]-15, area.width*.86, tile_h*(cols+row_count)*.54))
        for y in range(row_count):
            for x in range(cols):
                pos = (x,y)
                self._draw_floor_tile(project(pos), tile_w, tile_h, (x+y)%2 == 0, x, y)
                if pos in self.game.goals:
                    self._draw_goal(project(pos), tile_w, tile_h)

        now = pygame.time.get_ticks()
        animation = self.animation
        progress = 1.0
        if animation:
            progress = min(1.0, max(0.0, (now-animation.started_at)/animation.duration))
            if progress >= 1:
                self.animation = None
        moving = bool(animation and progress < 1)
        hero_pos: tuple[float,float] = self.game.player
        box_pos = None
        if moving and animation:
            ease = self._ease(progress)
            hero_pos = (animation.start[0]+(animation.end[0]-animation.start[0])*ease,
                        animation.start[1]+(animation.end[1]-animation.start[1])*ease)
            if animation.box_start is not None and animation.box_end is not None:
                box_pos = (animation.box_start[0]+(animation.box_end[0]-animation.box_start[0])*ease,
                           animation.box_start[1]+(animation.box_end[1]-animation.box_start[1])*ease)
        drawables = []
        for y in range(row_count):
            for x in range(cols):
                p = (x,y)
                if p in self.game.walls:
                    drawables.append((x+y,0,"wall",p))
                elif p in self.game.boxes and not (moving and animation and p == animation.box_end):
                    drawables.append((x+y,1,"crate",p))
        if box_pos is not None:
            drawables.append((sum(box_pos),1,"crate",box_pos))
        drawables.append((sum(hero_pos),2,"hero",hero_pos))
        for _, _, kind, pos in sorted(drawables, key=lambda item: (item[0],item[1])):
            ground = project(pos)
            if kind == "wall":
                self._draw_stone_block(ground, tile_w, tile_h, wall_h, round(pos[0]), round(pos[1]))
            elif kind == "crate":
                self._draw_crate(ground, tile_w, tile_h)
            else:
                started = animation.started_at if moving and animation else None
                self._draw_hero(ground, self.facing_row, moving, now, tile_h, started)

    def _draw_floor_tile(self, center: tuple[int,int], tile_w: int, tile_h: int, alternate: bool,
                         x: int = 0, y: int = 0) -> None:
        cx, cy = center
        hw, hh = tile_w//2, tile_h//2
        diamond = [(cx,cy-hh),(cx+hw,cy),(cx,cy+hh),(cx-hw,cy)]
        base = (57, 51, 77) if alternate else (49, 45, 70)
        pygame.draw.polygon(self.screen,(25, 24, 47), [(px, py+5) for px,py in diamond])
        pygame.draw.polygon(self.screen, base, diamond)
        pygame.draw.polygon(self.screen,(94, 84, 120),diamond,2)
        # Stable authored-looking stone scratches, independent of frame count.
        seed = x*1193+y*5791
        for i in range(3):
            sx = cx-hw//2+(seed+i*13)%(max(2,hw))
            sy = cy-hh//3+(seed//3+i*9)%(max(2,hh//2))
            pygame.draw.line(self.screen,(74,67,96),(sx,sy),(sx+7,sy-2),1)

    def _draw_stone_block(self, ground: tuple[int,int], tw: int, th: int, height: int, x: int, y: int) -> None:
        cx, cy = ground
        hw, hh = tw//2, th//2
        ty = cy-height
        top=[(cx,ty-hh),(cx+hw,ty),(cx,ty+hh),(cx-hw,ty)]
        left=[top[3],top[2],(cx,cy+hh),(cx-hw,cy)]
        right=[top[2],top[1],(cx+hw,cy),(cx,cy+hh)]
        pygame.draw.polygon(self.screen,(52,48,77),left)
        pygame.draw.polygon(self.screen,(40,38,66),right)
        pygame.draw.polygon(self.screen,(118+(x+y)%9,108+(x*7+y)%8,153+(x*5+y)%8),top)
        pygame.draw.polygon(self.screen,(168,156,190),top,2)
        pygame.draw.line(self.screen,(86,79,115),(cx-hw+5,cy-height//2),(cx-3,cy-height//2+hh-3),2)
        pygame.draw.line(self.screen,(88,78,116),(cx+5,ty-3),(cx+tw//5,ty+2),2)
        pygame.draw.circle(self.screen,(183,169,198),(cx-hw+7,ty-2),2)

    def _draw_crate(self, ground: tuple[int,int], tw: int, th: int) -> None:
        cx, cy = ground
        w, h = round(tw*.66), round(th*.90)
        hw, hh=w//2,h//2
        rise=round(th*1.27)
        ty=cy-rise
        top=[(cx,ty-hh),(cx+hw,ty),(cx,ty+hh),(cx-hw,ty)]
        front=(cx,ty+hh+rise)
        left=[top[3],top[2],front,(cx-hw,ty+rise)]
        right=[top[2],top[1],(cx+hw,ty+rise),front]
        pygame.draw.ellipse(self.screen,(13,15,30),(cx-hw,cy-3,w,max(13,th//2)))
        pygame.draw.polygon(self.screen,(141,75,35),left)
        pygame.draw.polygon(self.screen,(104,55,33),right)
        pygame.draw.polygon(self.screen,(223,143,63),top)
        for face in (left,right):
            pygame.draw.polygon(self.screen,(238,169,85),face,3)
        pygame.draw.polygon(self.screen,(255,190,104),top,3)
        pygame.draw.line(self.screen,(251,191,100),top[3],top[1],4)
        pygame.draw.line(self.screen,(128,67,35),top[0],top[2],3)
        pygame.draw.line(self.screen,(214,121,57),left[0],left[2],4)
        pygame.draw.line(self.screen,(178,91,47),right[1],right[3],4)
        for px,py in (top[0],top[1],top[2],top[3]):
            pygame.draw.circle(self.screen,(83,57,48),(px,py),2)

    def _draw_goal(self, center: tuple[int,int], tw: int, th: int) -> None:
        cx,cy=center
        self._glow((cx,cy),max(32,tw//2),(59,251,85),130)
        for i,c in ((0,(31,103,57)),(4,(86,246,76)),(10,(26,114,55))):
            r=max(8,tw//4-i)
            pygame.draw.ellipse(self.screen,c,(cx-r,cy-r//2,r*2,r),width=4)
        pygame.draw.circle(self.screen,(165,255,135),(cx,cy),4)

    def _draw_hero(self, ground: tuple[int,int], direction_row: int, moving: bool,
                   now: int, tile_h: int, animation_started_at: int|None=None) -> None:
        frame = min(3,(now-animation_started_at)//52) if moving and animation_started_at is not None else 0
        key=(tile_h,direction_row,frame)
        sprite=self._hero_cache.get(key)
        if sprite is None:
            source=self.hero_frames[direction_row][frame]
            target_h=round(tile_h*2.65)
            w,h=source.get_size()
            sprite=pygame.transform.smoothscale(source,(max(1,round(target_h*w/h)),target_h))
            self._hero_cache[key]=sprite
        shadow_y=ground[1]+tile_h//8
        pygame.draw.ellipse(self.screen,(16,14,32),(ground[0]-tile_h//2,shadow_y-4,tile_h,max(8,tile_h//3)))
        bob=0 if moving else round(math.sin(now/370)*2)
        self.screen.blit(sprite,sprite.get_rect(midbottom=(ground[0],shadow_y+8+bob)))

    def _panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen,(6,10,30),rect.move(0,8),border_radius=27)
        pygame.draw.rect(self.screen,PANEL,rect,border_radius=27)
        pygame.draw.rect(self.screen,(88,87,144),rect,3,border_radius=27)
        pygame.draw.line(self.screen,(107,99,164),(rect.x+23,rect.y+4),(rect.right-23,rect.y+4),2)

    def _button(self, rect: pygame.Rect, label: str, action: str, *, enabled: bool=True,
                primary: bool=False, size: int=18) -> None:
        hover=enabled and rect.collidepoint(self._ui_mouse())
        shadow=rect.move(0,6)
        pygame.draw.rect(self.screen,(6,8,27),shadow,border_radius=16)
        if not enabled:
            fill=(41,43,75); edge=(64,67,108); fg=(112,117,153)
        elif primary:
            fill=(59,174,45) if hover else (41,146,49)
            edge=(154,250,93); fg=WHITE
        else:
            fill=(64,65,122) if hover else (48,50,99)
            edge=(106,111,185); fg=WHITE
        pygame.draw.rect(self.screen,fill,rect,border_radius=16)
        pygame.draw.rect(self.screen,edge,rect,2,border_radius=16)
        pygame.draw.line(self.screen,tuple(min(255,c+30) for c in fill),
                         (rect.x+18,rect.y+4),(rect.right-18,rect.y+4),2)
        font=pygame.font.SysFont("dejavusans",size,bold=True)
        self._center_text(label,font,fg,rect.center)
        self.buttons.append(Button(rect,label,action,enabled,primary))

    def _draw_sidebar(self, rect: pygame.Rect) -> None:
        self._panel(rect)
        x,y=rect.x,rect.y
        self._center_text("Level",self.body_font,PERIWINKLE,(rect.centerx,y+39))
        self._button(pygame.Rect(x+18,y+69,52,56),"❮","previous_level",enabled=self.game.level_index>0,size=26)
        self._button(pygame.Rect(rect.right-70,y+69,52,56),"❯","following_level",enabled=self.game.level_index<len(self.game.levels)-1,size=26)
        self._center_text(f"{self.game.level_index+1} / {len(self.game.levels)}",self.number_font,WHITE,(rect.centerx,y+99))
        pygame.draw.line(self.screen,(91,90,150),(x+24,y+147),(rect.right-24,y+147),2)
        self._text("✦",self.heading_font,PERIWINKLE,(x+30,y+185))
        self._text("Moves",self.body_font,PERIWINKLE,(x+110,y+170))
        self._shadow_text(str(self.game.moves),self.number_font,GOLD,(x+109,y+197))
        self._text("★",self.heading_font,GOLD,(x+29,y+282))
        self._text("Best",self.body_font,PERIWINKLE,(x+110,y+272))
        best=self.best_moves.get(str(self.game.level_index))
        self._text(str(best) if best is not None else "—",self.number_font,WHITE,(x+108,y+301))
        pygame.draw.line(self.screen,(89,87,145),(x+24,y+367),(rect.right-24,y+367),2)
        self._text("Progress",self.body_font,PERIWINKLE,(x+27,y+389))
        prog_w=rect.width-108
        bar=pygame.Rect(x+27,y+431,prog_w,24)
        pygame.draw.rect(self.screen,(19,21,55),bar,border_radius=13)
        done=len(self.completed)
        if done:
            amount=max(8,round(bar.width*done/len(self.game.levels)))
            pygame.draw.rect(self.screen,GREEN,(bar.x,bar.y,amount,bar.height),border_radius=13)
        pygame.draw.rect(self.screen,(79,87,149),bar,2,border_radius=13)
        self._text(f"{round(100*done/len(self.game.levels))}%",self.body_font,WHITE,(x+rect.width-75,y+430))
        undo=pygame.Rect(x+27,y+491,115,99)
        redo=pygame.Rect(x+165,y+491,115,99)
        self._button(undo,"↶  Undo","undo",size=18)
        self._button(redo,"⟳  Restart","restart",size=17)
        self._button(pygame.Rect(x+25,y+621,rect.width-50,73),"▶   Next Level  ❯","next",
                     primary=True,enabled=self.game.is_won and self.game.level_index<len(self.game.levels)-1,size=20)

    def _draw_tip(self) -> None:
        rect=pygame.Rect(35,843,396,86)
        self._panel(rect)
        self._text("✦",self.number_font,GOLD,(rect.x+25,rect.y+18))
        self._text("Tip:",self.body_font,GOLD,(rect.x+87,rect.y+16))
        self._text("Plan your moves ahead!",self.small_font,WHITE,(rect.x+87,rect.y+47))
        self._text("Arrows / WASD · Z undo · R restart",self.small_font,PERIWINKLE,(510,886))

    def _shadow_text(self, value: str, font: pygame.font.Font,
                     color: tuple[int,int,int], pos: tuple[int,int]) -> None:
        self._text(value,font,(67,34,45),(pos[0]+3,pos[1]+5))
        self._text(value,font,color,pos)

    def _draw_win_overlay(self, area: pygame.Rect) -> None:
        tint=pygame.Surface(DESIGN_SIZE,pygame.SRCALPHA)
        tint.fill((12,11,31,128))
        self.screen.blit(tint,(0,0))
        card=pygame.Rect(area.centerx-290,area.centery-235,580,485)
        self._panel(card)
        self._popup_buttons=[]
        # Three glowing stars stay visually separate from level geometry.
        for cx,cy,r in ((card.centerx-135,card.y+29,31),(card.centerx,card.y+6,45),(card.centerx+135,card.y+29,31)):
            self._glow((cx,cy),r+34,(255,187,39),125)
            self._draw_star((cx,cy),r,(255,209,72))
        self._center_text("LEVEL COMPLETE!",self.title_font,GOLD,(card.centerx,card.y+143))
        self._center_text(f"Great job! Solved in {self.game.moves} moves.",self.body_font,WHITE,(card.centerx,card.y+207))
        pygame.draw.line(self.screen,(97,96,153),(card.x+65,card.y+251),(card.right-65,card.y+251),2)
        has_next=self.game.level_index+1<len(self.game.levels)
        big=pygame.Rect(card.x+75,card.y+273,card.width-150,72)
        label="▶   Next Level" if has_next else "★   All Levels Complete"
        self._popup_button(big,label,"next",enabled=has_next,primary=True,size=24)
        self._popup_button(pygame.Rect(card.x+70,card.y+369,197,63),"⟳   Retry","restart",size=19)
        self._popup_button(pygame.Rect(card.x+310,card.y+369,197,63),"⌂   Levels","menu",size=19)

    def _popup_button(self, rect: pygame.Rect, label: str, action: str, *,
                      enabled: bool=True, primary: bool=False, size: int=18) -> None:
        # _button registers in underlying HUD; move the result to the modal list.
        self._button(rect,label,action,enabled=enabled,primary=primary,size=size)
        self._popup_buttons.append(self.buttons.pop())