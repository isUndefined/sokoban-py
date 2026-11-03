"""Asset contract for production-ready Sokoban sprites (requires pygame-ce)."""
from pathlib import Path
import unittest

import pygame


ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'modern'


class ModernAssetTests(unittest.TestCase):
    def test_compatible_sizes_and_transparency(self):
        for name in ('floor', 'wall', 'crate', 'goal', 'player_up'):
            with self.subTest(name=name):
                path = ASSETS / f'{name}.png'
                self.assertTrue(path.exists())
                s = pygame.image.load(str(path))
                self.assertEqual(s.get_size(), (96, 96))
                self.assertEqual(s.get_at((48, 48)).a,
                                 0 if name == 'goal' else 255)
                if name == 'floor':
                    self.assertEqual(s.get_at((0, 0)).a, 255)
                else:
                    self.assertEqual(s.get_at((0, 0)).a, 0)

    def test_goal_is_a_transparent_ring(self):
        goal = pygame.image.load(str(ASSETS / 'goal.png'))
        self.assertGreater(goal.get_at((48, 20)).a, 150)
        self.assertEqual(goal.get_at((48, 48)).a, 0)

    def test_atlas_layout(self):
        atlas = pygame.image.load(str(ASSETS / 'atlas.png'))
        self.assertEqual(atlas.get_size(), (480, 96))


if __name__ == '__main__':
    unittest.main()
