"""A small, dependency-free terminal Sokoban game."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Iterable

Position = tuple[int, int]


@dataclass(frozen=True)
class Level:
    name: str
    rows: tuple[str, ...]


LEVELS = (
    Level("First steps", (
        "########",
        "#      #",
        "# . .  #",
        "# $$   #",
        "#  @   #",
        "#      #",
        "########",
    )),
    Level("Around the corner", (
        "#########",
        "#       #",
        "# .# .  #",
        "# $ $   #",
        "#   @   #",
        "#       #",
        "#########",
    )),
    Level("Three crates", (
        "##########",
        "#        #",
        "# .  . . #",
        "# $$$    #",
        "#   @    #",
        "#        #",
        "##########",
    )),
)

DIRECTIONS: dict[str, Position] = {
    "w": (0, -1), "up": (0, -1),
    "s": (0, 1), "down": (0, 1),
    "a": (-1, 0), "left": (-1, 0),
    "d": (1, 0), "right": (1, 0),
}


class Game:
    """Sokoban rules and state, independent from terminal input/output."""

    def __init__(self, levels: Iterable[Level] = LEVELS, level_index: int = 0):
        self.levels = tuple(levels)
        if not self.levels:
            raise ValueError("At least one level is required.")
        self.level_index = level_index
        self._load_level()

    def _load_level(self) -> None:
        level = self.levels[self.level_index]
        if not level.rows or any(len(row) != len(level.rows[0]) for row in level.rows):
            raise ValueError(f"Level '{level.name}' must be a non-empty rectangle.")

        self.walls: set[Position] = set()
        self.goals: set[Position] = set()
        self.boxes: set[Position] = set()
        players: list[Position] = []
        for y, row in enumerate(level.rows):
            for x, tile in enumerate(row):
                pos = (x, y)
                if tile == "#":
                    self.walls.add(pos)
                elif tile == ".":
                    self.goals.add(pos)
                elif tile == "$":
                    self.boxes.add(pos)
                elif tile == "@":
                    players.append(pos)
                elif tile == "+":
                    self.goals.add(pos)
                    players.append(pos)
                elif tile == "*":
                    self.goals.add(pos)
                    self.boxes.add(pos)
                elif tile != " ":
                    raise ValueError(f"Unknown tile {tile!r} in level '{level.name}'.")

        if len(players) != 1:
            raise ValueError(f"Level '{level.name}' must contain exactly one player.")
        if len(self.boxes) != len(self.goals):
            raise ValueError(f"Level '{level.name}' must have the same number of boxes and goals.")

        self.player = players[0]
        self.moves = 0
        self._history: list[tuple[Position, frozenset[Position], int]] = []

    @property
    def level(self) -> Level:
        return self.levels[self.level_index]

    @property
    def is_won(self) -> bool:
        return self.boxes == self.goals

    @property
    def boxes_on_goals(self) -> int:
        return len(self.boxes & self.goals)

    def move(self, dx: int, dy: int) -> bool:
        """Move one tile; push at most one box. Return False for blocked moves."""
        if (dx, dy) not in DIRECTIONS.values():
            raise ValueError("A move must be one orthogonal step.")
        destination = (self.player[0] + dx, self.player[1] + dy)
        if destination in self.walls:
            return False

        pushed_box = destination in self.boxes
        if pushed_box:
            beyond = (destination[0] + dx, destination[1] + dy)
            if beyond in self.walls or beyond in self.boxes:
                return False

        self._history.append((self.player, frozenset(self.boxes), self.moves))
        if pushed_box:
            self.boxes.remove(destination)
            self.boxes.add(beyond)
        self.player = destination
        self.moves += 1
        return True

    def undo(self) -> bool:
        if not self._history:
            return False
        self.player, previous_boxes, self.moves = self._history.pop()
        self.boxes = set(previous_boxes)
        return True

    def restart(self) -> None:
        self._load_level()

    def next_level(self) -> bool:
        if self.level_index + 1 >= len(self.levels):
            return False
        self.level_index += 1
        self._load_level()
        return True

    def render(self) -> str:
        width = len(self.level.rows[0])
        height = len(self.level.rows)
        output: list[str] = []
        for y in range(height):
            row: list[str] = []
            for x in range(width):
                pos = (x, y)
                if pos == self.player:
                    tile = "+" if pos in self.goals else "@"
                elif pos in self.boxes:
                    tile = "*" if pos in self.goals else "$"
                elif pos in self.walls:
                    tile = "#"
                elif pos in self.goals:
                    tile = "."
                else:
                    tile = " "
                row.append(tile)
            output.append("".join(row).rstrip())
        return "\n".join(output)


def play() -> None:
    parser = argparse.ArgumentParser(description="Play Sokoban in your terminal.")
    parser.add_argument("--level", type=int, default=1, help="starting level number (default: 1)")
    args = parser.parse_args()
    if not 1 <= args.level <= len(LEVELS):
        parser.error(f"--level must be between 1 and {len(LEVELS)}")

    game = Game(level_index=args.level - 1)
    print("SOKOBAN — push every crate onto a goal.\n")
    print("Controls: W/A/S/D or up/left/down/right | U undo | R restart | N next level | Q quit")

    while True:
        print(f"\nLevel {game.level_index + 1}/{len(game.levels)}: {game.level.name}")
        print(game.render())
        print(f"Moves: {game.moves} | Goals: {game.boxes_on_goals}/{len(game.goals)}")
        if game.is_won:
            if game.level_index == len(game.levels) - 1:
                print("\nCongratulations! You completed every level.")
                break
            print("\nLevel complete! Enter N for the next level, R to replay, or Q to quit.")

        try:
            command = input("Move> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if command in ("q", "quit", "exit"):
            print("Goodbye!")
            break
        if command in ("u", "undo"):
            if not game.undo():
                print("Nothing to undo.")
            continue
        if command in ("r", "restart"):
            game.restart()
            continue
        if command in ("n", "next"):
            if not game.is_won:
                print("Finish the current level before moving on.")
            elif not game.next_level():
                print("There are no more levels.")
            continue
        direction = DIRECTIONS.get(command)
        if direction is None:
            print("Unknown command. Use W/A/S/D, U, R, N, or Q.")
        elif not game.move(*direction):
            print("Blocked — you cannot move there.")


if __name__ == "__main__":
    play()
