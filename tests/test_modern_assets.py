"""Geometry/alpha contract for separately validated production candidate tiles."""
from pathlib import Path
import unittest
import pygame

ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'modern'
SPRITES = ('floor', 'wall', 'crate', 'goal', 'player_up')
EXPECTED_BOXES = {
    'wall': (3, 3, 90, 90),
    'crate': (8, 8, 80, 80),
    'goal': (16, 16, 64, 64),
    'player_up': (22, 9, 52, 78),
}


class ModernAssetTests(unittest.TestCase):
    def test_rgba_96px_and_centered_geometry(self):
        for name in SPRITES:
            with self.subTest(name=name):
                tile = pygame.image.load(str(ASSETS / f'{name}.png'))
                self.assertEqual(tile.get_size(), (96, 96))
                self.assertEqual(tile.get_bitsize(), 32)
                if name == 'floor':
                    self.assertEqual(tile.get_at((0, 0)).a, 255)
                    self.assertEqual(tile.get_at((48, 48)).a, 255)
                    continue
                # The former sprites had stray dark corners. Each of the four
                # corners must now be fully transparent on any background.
                for point in ((0, 0), (95, 0), (0, 95), (95, 95)):
                    self.assertEqual(tile.get_at(point).a, 0, (name, point))
                visible = [(x, y) for y in range(96) for x in range(96)
                           if tile.get_at((x, y)).a > 32]
                self.assertTrue(visible)
                x0 = min(x for x, _ in visible)
                x1 = max(x for x, _ in visible) + 1
                y0 = min(y for _, y in visible)
                y1 = max(y for _, y in visible) + 1
                self.assertEqual((x0, y0, x1-x0, y1-y0), EXPECTED_BOXES[name])
                self.assertEqual(x0 + x1, 96)
                self.assertEqual(y0 + y1, 96)

    def test_goal_is_ring_not_solid(self):
        goal = pygame.image.load(str(ASSETS / 'goal.png'))
        self.assertGreater(goal.get_at((48, 20)).a, 150)
        self.assertEqual(goal.get_at((48, 48)).a, 0)

    def test_atlas_compatibility(self):
        atlas = pygame.image.load(str(ASSETS / 'atlas.png'))
        self.assertEqual(atlas.get_size(), (5 * 96, 96))


if __name__ == '__main__':
    unittest.main()
